//! Input injection backend using /dev/uinput via the evdev crate.
//!
//! This operates at the kernel level and works on ALL Linux compositors
//! (Wayland and X11) because it bypasses the display server entirely.
//!
//! Requires the user to be in the `input` group or have write access to /dev/uinput.

pub mod keymap;
pub mod uinput;
