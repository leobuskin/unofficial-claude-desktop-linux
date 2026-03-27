//! Claude Native — Linux implementation of @ant/claude-native and @ant/claude-swift.
//!
//! Single native module providing:
//! - Input injection (keyboard, mouse) via /dev/uinput
//! - Screen/display queries (stubs, TODO: Wayland protocols)
//! - Process and app management
//! - Stubs for VM and notification subsystems
//!
//! Built with NAPI-RS, compiled to a .node binary.

#![deny(clippy::all)]

#[macro_use]
extern crate napi_derive;

mod input;
mod system;

use std::sync::OnceLock;

use input::uinput::UinputBackend;

// ---------------------------------------------------------------------------
// Lazy-initialized uinput backend
// ---------------------------------------------------------------------------

static UINPUT: OnceLock<Result<UinputBackend, String>> = OnceLock::new();

fn get_uinput() -> Result<&'static UinputBackend, String> {
    UINPUT
        .get_or_init(|| {
            // TODO: get actual screen dimensions from Wayland wl_output
            UinputBackend::new(1920, 1080)
        })
        .as_ref()
        .map_err(|e| e.clone())
}

// ===========================================================================
// @ant/claude-native API — Computer Use input methods
// ===========================================================================

/// Press a combination of keys simultaneously, then release in reverse order.
#[napi]
pub fn keys(key_names: Vec<String>) -> napi::Result<()> {
    get_uinput()
        .map_err(napi::Error::from_reason)?
        .keys(&key_names)
        .map_err(napi::Error::from_reason)
}

/// Press or release a single key.
#[napi]
pub fn key(key_name: String, action: String) -> napi::Result<()> {
    get_uinput()
        .map_err(napi::Error::from_reason)?
        .key(&key_name, &action)
        .map_err(napi::Error::from_reason)
}

/// Click, press, or release a mouse button.
#[napi]
pub fn mouse_button(button: String, action: String, count: Option<u32>) -> napi::Result<()> {
    get_uinput()
        .map_err(napi::Error::from_reason)?
        .mouse_button(&button, &action, count.unwrap_or(1))
        .map_err(napi::Error::from_reason)
}

/// Scroll the mouse wheel.
#[napi]
pub fn mouse_scroll(amount: i32, direction: String) -> napi::Result<()> {
    get_uinput()
        .map_err(napi::Error::from_reason)?
        .mouse_scroll(amount, &direction)
        .map_err(napi::Error::from_reason)
}

/// Move the mouse cursor to screen coordinates.
#[napi]
pub fn move_mouse(x: i32, y: i32, smooth: bool) -> napi::Result<()> {
    get_uinput()
        .map_err(napi::Error::from_reason)?
        .move_mouse(x, y, smooth)
        .map_err(napi::Error::from_reason)
}

/// Get the current mouse cursor position.
/// TODO: Replace with wlr-layer-shell overlay for real compositor position.
#[napi]
pub fn mouse_location() -> napi::Result<MousePosition> {
    let (x, y) = get_uinput()
        .map_err(napi::Error::from_reason)?
        .last_position();
    Ok(MousePosition {
        x: x as u32,
        y: y as u32,
    })
}

/// Type text using key events.
#[napi]
pub fn type_text(text: String) -> napi::Result<()> {
    get_uinput()
        .map_err(napi::Error::from_reason)?
        .type_text(&text)
        .map_err(napi::Error::from_reason)
}

/// Get information about the foreground application.
#[napi]
pub fn get_frontmost_app_info() -> napi::Result<Option<AppInfo>> {
    Ok(system::get_frontmost_app_info().map(|(bundle_id, app_name)| AppInfo {
        bundle_id,
        app_name,
    }))
}

/// Get app info for a file path (default handler).
#[napi]
pub fn get_app_info_for_file(path: String) -> napi::Result<Option<AppInfo>> {
    Ok(
        system::get_app_info_for_file(&path).map(|(bundle_id, app_name)| AppInfo {
            bundle_id,
            app_name,
        }),
    )
}

/// Check if a process with the given name is running.
#[napi]
pub fn is_process_running(name: String) -> bool {
    system::is_process_running(&name)
}

// ===========================================================================
// @ant/claude-native API — existing types and stubs
// ===========================================================================

#[napi(object)]
pub struct MousePosition {
    pub x: u32,
    pub y: u32,
}

#[napi(object)]
pub struct AppInfo {
    pub bundle_id: String,
    pub app_name: String,
}

#[napi]
pub enum KeyboardKey {
    Num0, Num1, Num2, Num3, Num4, Num5, Num6, Num7, Num8, Num9,
    A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z,
    AbntC1, AbntC2, Accept, Add, Alt, Apps, Attn, Backspace, Break, Begin,
    BrightnessDown, BrightnessUp, BrowserBack, BrowserFavorites, BrowserForward,
    BrowserHome, BrowserRefresh, BrowserSearch, BrowserStop, Cancel, CapsLock,
    Clear, Command, ContrastUp, ContrastDown, Control, Convert, Crsel,
    DBEAlphanumeric, DBECodeinput, DBEDetermineString, DBEEnterDLGConversionMode,
    DBEEnterIMEConfigMode, DBEEnterWordRegisterMode, DBEFlushString, DBEHiragana,
    DBEKatakana, DBENoCodepoint, DBENoRoman, DBERoman, DBESBCSChar, DBESChar,
    Decimal, Delete, Divide, DownArrow, Eject, End, Ereof, Escape, Execute, Excel,
    F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12,
    F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24,
    F25, F26, F27, F28, F29, F30, F31, F32, F33, F34, F35,
    Function, Final, Find, GamepadA, GamepadB, GamepadDPadDown, GamepadDPadLeft,
    GamepadDPadRight, GamepadDPadUp, GamepadLeftShoulder, GamepadLeftThumbstickButton,
    GamepadLeftThumbstickDown, GamepadLeftThumbstickLeft, GamepadLeftThumbstickRight,
    GamepadLeftThumbstickUp, GamepadLeftTrigger, GamepadMenu, GamepadRightShoulder,
    GamepadRightThumbstickButton, GamepadRightThumbstickDown, GamepadRightThumbstickLeft,
    GamepadRightThumbstickRight, GamepadRightThumbstickUp, GamepadRightTrigger,
    GamepadView, GamepadX, GamepadY, Hangeul, Hangul, Hanja, Help, Home,
    Ico00, IcoClear, IcoHelp, IlluminationDown, IlluminationUp, IlluminationToggle,
    IMEOff, IMEOn, Insert, Junja, Kana, Kanji, LaunchApp1, LaunchApp2, LaunchMail,
    LaunchMediaSelect, Launchpad, LaunchPanel, LButton, LControl, LeftArrow,
    Linefeed, LMenu, LShift, LWin, MButton, MediaFast, MediaNextTrack,
    MediaPlayPause, MediaPrevTrack, MediaRewind, MediaStop, Meta, MissionControl,
    ModeChange, Multiply, NavigationAccept, NavigationCancel, NavigationDown,
    NavigationLeft, NavigationMenu, NavigationRight, NavigationUp, NavigationView,
    NoName, NonConvert, None, Numlock, Numpad0, Numpad1, Numpad2, Numpad3,
    Numpad4, Numpad5, Numpad6, Numpad7, Numpad8, Numpad9,
    OEM1, OEM102, OEM2, OEM3, OEM4, OEM5, OEM6, OEM7, OEM8,
    OEMAttn, OEMAuto, OEMAx, OEMBacktab, OEMClear, OEMComma, OEMCopy, OEMCusel,
    OEMEnlw, OEMFinish, OEMFJJisho, OEMFJLoya, OEMFJMasshou, OEMFJRoya,
    OEMFJTouroku, OEMJump, OEMMinus, OEMNECEqual, OEMPA1, OEMPA2, OEMPA3,
    OEMPeriod, OEMPlus, OEMReset, OEMWsctrl, Option, PA1, Packet, PageDown,
    PageUp, Pause, Play, Power, Print, Processkey, RButton, RCommand, RControl,
    Redo, Return, RightArrow, RMenu, ROption, RShift, RWin, Scroll, ScrollLock,
    Select, ScriptSwitch, Separator, Shift, ShiftLock, Sleep, Snapshot, Space,
    Subtract, Super, SysReq, Tab, Undo, UpArrow, VidMirror, VolumeDown,
    VolumeMute, VolumeUp, MicMute, Windows, XButton1, XButton2, Zoom,
}

#[napi]
pub enum ScrollDirection {
    Down = 0,
    Up = 1,
}

// Note: This enum shadows the mouseButton function name in JS.
// NAPI-RS generates MouseButton as a JS enum/object, which doesn't conflict
// with the mouseButton function export.
#[napi(js_name = "MouseButtonEnum")]
pub enum MouseButtonKind {
    Left = 0,
    Middle = 1,
    Right = 2,
}

#[napi]
pub enum RequestAccessibilityOptions {
    ShowDialog,
    OnlyRegisterInSettings,
}

#[napi(object)]
pub struct MonitorInfo {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
    pub monitor_name: String,
    pub is_primary: bool,
}

#[napi(object)]
pub struct WindowInfo {
    pub handle: u32,
    pub process_id: u32,
    pub executable_path: String,
    pub title: String,
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

#[napi]
pub fn request_accessibility(_options: i32) -> bool {
    true // No TCC on Linux
}

#[napi]
pub fn get_window_info() -> Vec<WindowInfo> {
    vec![]
}

#[napi]
pub fn get_active_window_handle() -> u32 {
    0
}

#[napi]
pub fn get_monitor_info() -> MonitorInfo {
    // TODO: Get real monitor info from Wayland wl_output
    MonitorInfo {
        x: 0,
        y: 0,
        width: 1920,
        height: 1080,
        monitor_name: "default".to_string(),
        is_primary: true,
    }
}

#[napi]
pub fn focus_window(_handle: u32) {}

// InputEmulator class (legacy API, kept for compatibility)
#[napi(constructor)]
pub struct InputEmulator {}

#[napi]
impl InputEmulator {
    #[napi]
    pub fn copy(&self) {}
    #[napi]
    pub fn cut(&self) {}
    #[napi]
    pub fn paste(&self) {}
    #[napi]
    pub fn undo(&self) {}
    #[napi]
    pub fn select_all(&self) {}
    #[napi]
    pub fn held(&self) -> Vec<u16> {
        vec![]
    }
    #[napi]
    pub fn press_chars(&self, _text: String) {}
    #[napi]
    pub fn press_key(&self, _key: Vec<i32>) {}
    #[napi]
    pub fn press_then_release_key(_key: Vec<i32>) {}
    #[napi]
    pub fn release_chars(&self, _text: String) {}
    #[napi]
    pub fn release_key(&self, _key: u32) {}
    #[napi]
    pub fn set_button_click(&self, _button: i32) {}
    #[napi]
    pub fn set_button_toggle(&self, _button: i32) {}
    #[napi]
    pub fn get_mouse_position(&self) -> MousePosition {
        MousePosition { x: 0, y: 0 }
    }
    #[napi(js_name = "typeText")]
    pub fn ie_type_text(&self, _text: String) {}
    #[napi]
    pub fn set_mouse_scroll(&self, _direction: i32, _amount: i32) {}
}

// AuthRequest class (not available on Linux)
#[napi]
pub struct AuthRequest {}

#[napi]
impl AuthRequest {
    #[napi(constructor)]
    pub fn new() -> Self {
        AuthRequest {}
    }
    #[napi(js_name = "isAvailable")]
    pub fn is_available() -> bool {
        false
    }
    #[napi]
    pub fn start(
        &self,
        _url: String,
        _scheme: String,
        _handle: napi::bindgen_prelude::Buffer,
    ) -> napi::Result<()> {
        Err(napi::Error::from_reason(
            "AuthRequest not available on Linux",
        ))
    }
    #[napi]
    pub fn cancel(&self) {}
}
