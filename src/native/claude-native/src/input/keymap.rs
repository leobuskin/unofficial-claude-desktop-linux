//! Maps string key names (as used by Claude's Computer Use API) to Linux evdev keycodes.
//!
//! The Computer Use API sends key names like "ctrl", "shift", "a", "Return", "space", etc.
//! This module converts those to evdev KEY_* constants for uinput injection.

use evdev::KeyCode;

/// Map a Computer Use key name string to an evdev Key.
///
/// Key names come from the macOS executor and follow Apple naming conventions.
/// We map them to Linux evdev equivalents.
pub fn resolve_key(name: &str) -> Option<KeyCode> {
    // Case-insensitive matching for modifier names, case-sensitive for single chars
    match name {
        // Modifiers
        "ctrl" | "control" | "Control" => Some(KeyCode::KEY_LEFTCTRL),
        "shift" | "Shift" => Some(KeyCode::KEY_LEFTSHIFT),
        "alt" | "Alt" | "option" | "Option" => Some(KeyCode::KEY_LEFTALT),
        "super" | "Super" | "command" | "Command" | "cmd" | "meta" | "Meta" => {
            Some(KeyCode::KEY_LEFTMETA)
        }
        "rctrl" | "RControl" => Some(KeyCode::KEY_RIGHTCTRL),
        "rshift" | "RShift" => Some(KeyCode::KEY_RIGHTSHIFT),
        "ralt" | "RAlt" | "roption" | "ROption" => Some(KeyCode::KEY_RIGHTALT),
        "rsuper" | "RSuper" | "rcommand" | "RCommand" => Some(KeyCode::KEY_RIGHTMETA),

        // Navigation
        "Return" | "return" | "enter" | "Enter" => Some(KeyCode::KEY_ENTER),
        "Tab" | "tab" => Some(KeyCode::KEY_TAB),
        "Escape" | "escape" | "esc" => Some(KeyCode::KEY_ESC),
        "space" | "Space" => Some(KeyCode::KEY_SPACE),
        "BackSpace" | "backspace" | "Backspace" => Some(KeyCode::KEY_BACKSPACE),
        "Delete" | "delete" => Some(KeyCode::KEY_DELETE),
        "Insert" | "insert" => Some(KeyCode::KEY_INSERT),
        "Home" | "home" => Some(KeyCode::KEY_HOME),
        "End" | "end" => Some(KeyCode::KEY_END),
        "Page_Up" | "pageup" | "PageUp" => Some(KeyCode::KEY_PAGEUP),
        "Page_Down" | "pagedown" | "PageDown" => Some(KeyCode::KEY_PAGEDOWN),

        // Arrow keys
        "Up" | "up" | "UpArrow" => Some(KeyCode::KEY_UP),
        "Down" | "down" | "DownArrow" => Some(KeyCode::KEY_DOWN),
        "Left" | "left" | "LeftArrow" => Some(KeyCode::KEY_LEFT),
        "Right" | "right" | "RightArrow" => Some(KeyCode::KEY_RIGHT),

        // Function keys
        "F1" | "f1" => Some(KeyCode::KEY_F1),
        "F2" | "f2" => Some(KeyCode::KEY_F2),
        "F3" | "f3" => Some(KeyCode::KEY_F3),
        "F4" | "f4" => Some(KeyCode::KEY_F4),
        "F5" | "f5" => Some(KeyCode::KEY_F5),
        "F6" | "f6" => Some(KeyCode::KEY_F6),
        "F7" | "f7" => Some(KeyCode::KEY_F7),
        "F8" | "f8" => Some(KeyCode::KEY_F8),
        "F9" | "f9" => Some(KeyCode::KEY_F9),
        "F10" | "f10" => Some(KeyCode::KEY_F10),
        "F11" | "f11" => Some(KeyCode::KEY_F11),
        "F12" | "f12" => Some(KeyCode::KEY_F12),

        // Toggles
        "Caps_Lock" | "capslock" | "CapsLock" => Some(KeyCode::KEY_CAPSLOCK),
        "Num_Lock" | "numlock" | "NumLock" => Some(KeyCode::KEY_NUMLOCK),
        "Scroll_Lock" | "scrolllock" | "ScrollLock" => Some(KeyCode::KEY_SCROLLLOCK),

        // Punctuation & symbols (US layout)
        "minus" | "-" => Some(KeyCode::KEY_MINUS),
        "equal" | "=" => Some(KeyCode::KEY_EQUAL),
        "bracketleft" | "[" => Some(KeyCode::KEY_LEFTBRACE),
        "bracketright" | "]" => Some(KeyCode::KEY_RIGHTBRACE),
        "backslash" | "\\" => Some(KeyCode::KEY_BACKSLASH),
        "semicolon" | ";" => Some(KeyCode::KEY_SEMICOLON),
        "apostrophe" | "'" => Some(KeyCode::KEY_APOSTROPHE),
        "grave" | "`" => Some(KeyCode::KEY_GRAVE),
        "comma" | "," => Some(KeyCode::KEY_COMMA),
        "period" | "." => Some(KeyCode::KEY_DOT),
        "slash" | "/" => Some(KeyCode::KEY_SLASH),

        // Print/Pause
        "Print" | "print" | "PrintScreen" => Some(KeyCode::KEY_PRINT),
        "Pause" | "pause" => Some(KeyCode::KEY_PAUSE),

        // Media keys
        "AudioMute" | "VolumeMute" => Some(KeyCode::KEY_MUTE),
        "AudioLowerVolume" | "VolumeDown" => Some(KeyCode::KEY_VOLUMEDOWN),
        "AudioRaiseVolume" | "VolumeUp" => Some(KeyCode::KEY_VOLUMEUP),
        "MediaPlayPause" => Some(KeyCode::KEY_PLAYPAUSE),
        "MediaNextTrack" => Some(KeyCode::KEY_NEXTSONG),
        "MediaPrevTrack" => Some(KeyCode::KEY_PREVIOUSSONG),
        "MediaStop" => Some(KeyCode::KEY_STOPCD),

        // Single character keys
        _ => resolve_char_key(name),
    }
}

/// Map a single-character key name to an evdev Key.
fn resolve_char_key(name: &str) -> Option<KeyCode> {
    if name.len() != 1 {
        return None;
    }
    let ch = name.chars().next()?;
    match ch {
        'a' | 'A' => Some(KeyCode::KEY_A),
        'b' | 'B' => Some(KeyCode::KEY_B),
        'c' | 'C' => Some(KeyCode::KEY_C),
        'd' | 'D' => Some(KeyCode::KEY_D),
        'e' | 'E' => Some(KeyCode::KEY_E),
        'f' | 'F' => Some(KeyCode::KEY_F),
        'g' | 'G' => Some(KeyCode::KEY_G),
        'h' | 'H' => Some(KeyCode::KEY_H),
        'i' | 'I' => Some(KeyCode::KEY_I),
        'j' | 'J' => Some(KeyCode::KEY_J),
        'k' | 'K' => Some(KeyCode::KEY_K),
        'l' | 'L' => Some(KeyCode::KEY_L),
        'm' | 'M' => Some(KeyCode::KEY_M),
        'n' | 'N' => Some(KeyCode::KEY_N),
        'o' | 'O' => Some(KeyCode::KEY_O),
        'p' | 'P' => Some(KeyCode::KEY_P),
        'q' | 'Q' => Some(KeyCode::KEY_Q),
        'r' | 'R' => Some(KeyCode::KEY_R),
        's' | 'S' => Some(KeyCode::KEY_S),
        't' | 'T' => Some(KeyCode::KEY_T),
        'u' | 'U' => Some(KeyCode::KEY_U),
        'v' | 'V' => Some(KeyCode::KEY_V),
        'w' | 'W' => Some(KeyCode::KEY_W),
        'x' | 'X' => Some(KeyCode::KEY_X),
        'y' | 'Y' => Some(KeyCode::KEY_Y),
        'z' | 'Z' => Some(KeyCode::KEY_Z),
        '0' | ')' => Some(KeyCode::KEY_0),
        '1' | '!' => Some(KeyCode::KEY_1),
        '2' | '@' => Some(KeyCode::KEY_2),
        '3' | '#' => Some(KeyCode::KEY_3),
        '4' | '$' => Some(KeyCode::KEY_4),
        '5' | '%' => Some(KeyCode::KEY_5),
        '6' | '^' => Some(KeyCode::KEY_6),
        '7' | '&' => Some(KeyCode::KEY_7),
        '8' | '*' => Some(KeyCode::KEY_8),
        '9' | '(' => Some(KeyCode::KEY_9),
        ' ' => Some(KeyCode::KEY_SPACE),
        _ => None,
    }
}

/// Check if a character requires Shift to type on a US keyboard layout.
pub fn needs_shift(ch: char) -> bool {
    matches!(
        ch,
        'A'..='Z'
            | '!'
            | '@'
            | '#'
            | '$'
            | '%'
            | '^'
            | '&'
            | '*'
            | '('
            | ')'
            | '_'
            | '+'
            | '{'
            | '}'
            | '|'
            | ':'
            | '"'
            | '<'
            | '>'
            | '?'
            | '~'
    )
}
