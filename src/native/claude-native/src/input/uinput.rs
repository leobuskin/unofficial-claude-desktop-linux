//! uinput-based input injection backend.
//!
//! Creates a virtual input device via /dev/uinput and injects keyboard, mouse,
//! and scroll events at the kernel level. Works on all compositors.

use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use evdev::uinput::VirtualDevice;
use evdev::{AbsInfo, AbsoluteAxisCode, AttributeSet, EventType, InputEvent, KeyCode, RelativeAxisCode, UinputAbsSetup};

use super::keymap;

/// Default screen dimensions for absolute mouse positioning.
/// These define the range of the virtual absolute device.
const ABS_MAX_X: i32 = 32767;
const ABS_MAX_Y: i32 = 32767;

/// Delay between key events to ensure the compositor processes them in order.
const EVENT_DELAY: Duration = Duration::from_micros(500);

/// Manages a virtual uinput device for input injection.
pub struct UinputBackend {
    device: Mutex<VirtualDevice>,
    /// Track the last absolute position we set (for mouseLocation).
    last_x: Mutex<i32>,
    last_y: Mutex<i32>,
    /// Screen dimensions for coordinate mapping.
    screen_width: i32,
    screen_height: i32,
}

impl UinputBackend {
    /// Create a new uinput backend with the given screen dimensions.
    pub fn new(screen_width: i32, screen_height: i32) -> Result<Self, String> {
        let device = Self::create_device()?;
        Ok(Self {
            device: Mutex::new(device),
            last_x: Mutex::new(0),
            last_y: Mutex::new(0),
            screen_width,
            screen_height,
        })
    }

    fn create_device() -> Result<VirtualDevice, String> {
        let err_hint = ". Is /dev/uinput accessible? Try: sudo usermod -aG input $USER";

        // Keyboard keys
        let mut keys = AttributeSet::<KeyCode>::new();
        for code in 1..=249 {
            keys.insert(KeyCode(code));
        }
        // Mouse buttons
        keys.insert(KeyCode::BTN_LEFT);
        keys.insert(KeyCode::BTN_RIGHT);
        keys.insert(KeyCode::BTN_MIDDLE);

        // Absolute axes for mouse positioning
        let abs_x = UinputAbsSetup::new(
            AbsoluteAxisCode::ABS_X,
            AbsInfo::new(0, 0, ABS_MAX_X, 0, 0, 1),
        );
        let abs_y = UinputAbsSetup::new(
            AbsoluteAxisCode::ABS_Y,
            AbsInfo::new(0, 0, ABS_MAX_Y, 0, 0, 1),
        );

        // Relative axes for scroll
        let mut rel_axes = AttributeSet::<RelativeAxisCode>::new();
        rel_axes.insert(RelativeAxisCode::REL_WHEEL);
        rel_axes.insert(RelativeAxisCode::REL_HWHEEL);

        VirtualDevice::builder()
            .map_err(|e| format!("Failed to create uinput builder: {e}{err_hint}"))?
            .name("Claude Desktop Virtual Input")
            .with_keys(&keys)
            .map_err(|e| format!("Failed to set keys: {e}"))?
            .with_absolute_axis(&abs_x)
            .map_err(|e| format!("Failed to set abs X: {e}"))?
            .with_absolute_axis(&abs_y)
            .map_err(|e| format!("Failed to set abs Y: {e}"))?
            .with_relative_axes(&rel_axes)
            .map_err(|e| format!("Failed to set rel axes: {e}"))?
            .build()
            .map_err(|e| format!("Failed to build uinput device: {e}{err_hint}"))
    }

    fn emit(&self, events: &[InputEvent]) -> Result<(), String> {
        let mut dev = self.device.lock().map_err(|e| format!("Lock error: {e}"))?;
        dev.emit(events)
            .map_err(|e| format!("Failed to emit events: {e}"))
    }

    fn syn(&self) -> Result<(), String> {
        self.emit(&[InputEvent::new(EventType::SYNCHRONIZATION.0, 0, 0)])
    }

    fn key_event(&self, key: KeyCode, value: i32) -> Result<(), String> {
        self.emit(&[InputEvent::new(EventType::KEY.0, key.0, value)])?;
        self.syn()
    }

    /// Map screen coordinates to the virtual device's absolute range.
    fn map_x(&self, x: i32) -> i32 {
        if self.screen_width <= 0 {
            return x;
        }
        (x as i64 * ABS_MAX_X as i64 / self.screen_width as i64) as i32
    }

    fn map_y(&self, y: i32) -> i32 {
        if self.screen_height <= 0 {
            return y;
        }
        (y as i64 * ABS_MAX_Y as i64 / self.screen_height as i64) as i32
    }

    // --- Public API matching Computer Use requirements ---

    /// Press a combination of keys simultaneously, then release in reverse order.
    /// e.g. keys(["ctrl", "c"]) → press Ctrl, press C, release C, release Ctrl.
    pub fn keys(&self, key_names: &[String]) -> Result<(), String> {
        let resolved: Vec<KeyCode> = key_names
            .iter()
            .map(|name| {
                keymap::resolve_key(name)
                    .ok_or_else(|| format!("Unknown key name: '{name}'"))
            })
            .collect::<Result<Vec<_>, _>>()?;

        // Press all keys in order
        for &key in &resolved {
            self.key_event(key, 1)?; // 1 = press
            thread::sleep(EVENT_DELAY);
        }

        // Release in reverse order
        for &key in resolved.iter().rev() {
            self.key_event(key, 0)?; // 0 = release
            thread::sleep(EVENT_DELAY);
        }

        Ok(())
    }

    /// Press or release a single key.
    pub fn key(&self, name: &str, action: &str) -> Result<(), String> {
        let key = keymap::resolve_key(name)
            .ok_or_else(|| format!("Unknown key name: '{name}'"))?;
        let value = match action {
            "press" => 1,
            "release" => 0,
            _ => return Err(format!("Unknown key action: '{action}'")),
        };
        self.key_event(key, value)
    }

    /// Click, press, or release a mouse button.
    pub fn mouse_button(&self, button: &str, action: &str, count: u32) -> Result<(), String> {
        let btn = match button {
            "left" => KeyCode::BTN_LEFT,
            "right" => KeyCode::BTN_RIGHT,
            "middle" => KeyCode::BTN_MIDDLE,
            _ => return Err(format!("Unknown mouse button: '{button}'")),
        };

        match action {
            "click" => {
                for _ in 0..count.max(1) {
                    self.key_event(btn, 1)?;
                    thread::sleep(Duration::from_millis(10));
                    self.key_event(btn, 0)?;
                    thread::sleep(Duration::from_millis(10));
                }
            }
            "press" => self.key_event(btn, 1)?,
            "release" => self.key_event(btn, 0)?,
            _ => return Err(format!("Unknown mouse action: '{action}'")),
        }

        Ok(())
    }

    /// Scroll the mouse wheel.
    pub fn mouse_scroll(&self, amount: i32, direction: &str) -> Result<(), String> {
        let axis = match direction {
            "vertical" => RelativeAxisCode::REL_WHEEL,
            "horizontal" => RelativeAxisCode::REL_HWHEEL,
            _ => return Err(format!("Unknown scroll direction: '{direction}'")),
        };

        self.emit(&[InputEvent::new(EventType::RELATIVE.0, axis.0, amount)])?;
        self.syn()
    }

    /// Move the mouse cursor to absolute screen coordinates.
    pub fn move_mouse(&self, x: i32, y: i32, smooth: bool) -> Result<(), String> {
        if smooth {
            self.smooth_move(x, y)?;
        } else {
            self.set_position(x, y)?;
        }
        Ok(())
    }

    fn set_position(&self, x: i32, y: i32) -> Result<(), String> {
        let abs_x = self.map_x(x);
        let abs_y = self.map_y(y);

        self.emit(&[
            InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_X.0, abs_x),
            InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_Y.0, abs_y),
        ])?;
        self.syn()?;

        *self.last_x.lock().map_err(|e| format!("Lock error: {e}"))? = x;
        *self.last_y.lock().map_err(|e| format!("Lock error: {e}"))? = y;

        Ok(())
    }

    fn smooth_move(&self, target_x: i32, target_y: i32) -> Result<(), String> {
        let start_x = *self.last_x.lock().map_err(|e| format!("Lock: {e}"))?;
        let start_y = *self.last_y.lock().map_err(|e| format!("Lock: {e}"))?;

        let steps = 30;
        let step_delay = Duration::from_millis(5);

        for i in 1..=steps {
            let t = i as f64 / steps as f64;
            // Ease-out cubic
            let eased = 1.0 - (1.0 - t).powi(3);
            let cx = start_x as f64 + (target_x - start_x) as f64 * eased;
            let cy = start_y as f64 + (target_y - start_y) as f64 * eased;
            self.set_position(cx as i32, cy as i32)?;
            thread::sleep(step_delay);
        }

        Ok(())
    }

    /// Get the last known mouse position.
    /// Note: this returns the last position we SET, not the actual cursor position.
    /// For actual cursor position, use the query backend.
    pub fn last_position(&self) -> (i32, i32) {
        let x = self.last_x.lock().map(|v| *v).unwrap_or(0);
        let y = self.last_y.lock().map(|v| *v).unwrap_or(0);
        (x, y)
    }

    /// Type text by converting each character to key events.
    /// ASCII characters are typed via keycodes. Non-ASCII characters are skipped
    /// (the caller should use the Wayland virtual keyboard protocol for Unicode).
    pub fn type_text(&self, text: &str) -> Result<(), String> {
        for ch in text.chars() {
            if let Some(key) = keymap::resolve_key(&ch.to_string()) {
                if keymap::needs_shift(ch) {
                    self.key_event(KeyCode::KEY_LEFTSHIFT, 1)?;
                    thread::sleep(EVENT_DELAY);
                    self.key_event(key, 1)?;
                    thread::sleep(EVENT_DELAY);
                    self.key_event(key, 0)?;
                    thread::sleep(EVENT_DELAY);
                    self.key_event(KeyCode::KEY_LEFTSHIFT, 0)?;
                } else {
                    self.key_event(key, 1)?;
                    thread::sleep(EVENT_DELAY);
                    self.key_event(key, 0)?;
                }
                thread::sleep(EVENT_DELAY);
            }
            // Non-ASCII characters silently skipped for now
        }
        Ok(())
    }
}
