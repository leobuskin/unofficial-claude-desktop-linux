//! System utilities: process checking, file associations, frontmost app.

use std::fs;
use std::process::Command;

/// Check if a process with the given name is running by scanning /proc.
pub fn is_process_running(name: &str) -> bool {
    let Ok(entries) = fs::read_dir("/proc") else {
        return false;
    };

    for entry in entries.flatten() {
        let path = entry.path();
        // Only check numeric directories (PIDs)
        if !path
            .file_name()
            .and_then(|n| n.to_str())
            .is_some_and(|n| n.chars().all(|c| c.is_ascii_digit()))
        {
            continue;
        }

        // Read /proc/<pid>/comm for the process name
        let comm_path = path.join("comm");
        if let Ok(comm) = fs::read_to_string(&comm_path) {
            if comm.trim() == name {
                return true;
            }
        }
    }
    false
}

/// Get the default application for a file path using xdg-mime.
pub fn get_app_info_for_file(path: &str) -> Option<(String, String)> {
    // Get MIME type
    let mime_output = Command::new("xdg-mime")
        .args(["query", "filetype", path])
        .output()
        .ok()?;
    let mime_type = String::from_utf8_lossy(&mime_output.stdout).trim().to_string();
    if mime_type.is_empty() {
        return None;
    }

    // Get default app for MIME type
    let app_output = Command::new("xdg-mime")
        .args(["query", "default", &mime_type])
        .output()
        .ok()?;
    let desktop_file = String::from_utf8_lossy(&app_output.stdout)
        .trim()
        .to_string();
    if desktop_file.is_empty() {
        return None;
    }

    // Extract app name from .desktop file name
    let app_name = desktop_file
        .strip_suffix(".desktop")
        .unwrap_or(&desktop_file)
        .to_string();
    Some((desktop_file, app_name))
}

/// Get information about the foreground application.
///
/// This is a stub that uses /proc and compositor-specific methods.
/// For now, returns None — the Wayland query backend will provide the real implementation.
pub fn get_frontmost_app_info() -> Option<(String, String)> {
    // TODO: Implement via ext_foreign_toplevel_list_v1 or compositor D-Bus
    None
}
