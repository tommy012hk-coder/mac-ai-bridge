import AppKit
import CoreGraphics
import Foundation
import ScreenCaptureKit
import Vision

struct BridgeFailure: Error, CustomStringConvertible {
    let description: String
}

func postKey(_ code: CGKeyCode, flags: CGEventFlags = []) throws {
    guard let source = CGEventSource(stateID: .hidSystemState),
          let down = CGEvent(keyboardEventSource: source, virtualKey: code, keyDown: true),
          let up = CGEvent(keyboardEventSource: source, virtualKey: code, keyDown: false) else {
        throw BridgeFailure(description: "Could not create a macOS keyboard event")
    }
    down.flags = flags
    up.flags = flags
    down.post(tap: .cghidEventTap)
    up.post(tap: .cghidEventTap)
}

func postClick(_ point: CGPoint) throws {
    guard let source = CGEventSource(stateID: .hidSystemState),
          let down = CGEvent(mouseEventSource: source, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left),
          let up = CGEvent(mouseEventSource: source, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left) else {
        throw BridgeFailure(description: "Could not create a macOS mouse event")
    }
    down.post(tap: .cghidEventTap)
    up.post(tap: .cghidEventTap)
}

func captureWindow(bundleID: String) async throws -> (CGImage, CGRect) {
    let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
    let application = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).first
    let windows = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] ?? []
    let frontmostWindowID = windows.first { info in
        guard let pid = info[kCGWindowOwnerPID as String] as? pid_t,
              let layer = info[kCGWindowLayer as String] as? Int,
              layer == 0,
              let bounds = info[kCGWindowBounds as String] as? [String: CGFloat],
              (bounds["Width"] ?? 0) > 300,
              (bounds["Height"] ?? 0) > 300 else {
            return false
        }
        return application?.processIdentifier == pid
    }?[kCGWindowNumber as String] as? CGWindowID
    guard let window = content.windows.first(where: {
        $0.owningApplication?.bundleIdentifier == bundleID &&
        (frontmostWindowID == nil || $0.windowID == frontmostWindowID)
    }) else {
        throw BridgeFailure(description: "No visible app window found; bring the target app window onto the current desktop")
    }
    let filter = SCContentFilter(desktopIndependentWindow: window)
    let configuration = SCStreamConfiguration()
    configuration.width = max(1, Int(window.frame.width * 2))
    configuration.height = max(1, Int(window.frame.height * 2))
    configuration.showsCursor = false
    let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: configuration)
    return (image, window.frame)
}

func recognizeText(_ image: CGImage) throws -> [String] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    try VNImageRequestHandler(cgImage: image).perform([request])
    return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
}

func saveClipboard(_ pasteboard: NSPasteboard) -> [[(NSPasteboard.PasteboardType, Data)]] {
    (pasteboard.pasteboardItems ?? []).map { item in
        item.types.compactMap { type in
            item.data(forType: type).map { (type, $0) }
        }
    }
}

func restoreClipboard(_ pasteboard: NSPasteboard, savedItems: [[(NSPasteboard.PasteboardType, Data)]]) {
    pasteboard.clearContents()
    let items = savedItems.compactMap { savedItem -> NSPasteboardItem? in
        let item = NSPasteboardItem()
        for (type, data) in savedItem {
            item.setData(data, forType: type)
        }
        return savedItem.isEmpty ? nil : item
    }
    if !items.isEmpty {
        pasteboard.writeObjects(items)
    }
}

func currentText(bundleID: String) async throws -> [String] {
    let (image, _) = try await captureWindow(bundleID: bundleID)
    return try recognizeText(image)
}

func run() async throws {
    let args = CommandLine.arguments
    guard args.count == 6 else {
        throw BridgeFailure(description: "Internal error: expected app ID, process, shortcut flag, prompt, and timeout")
    }
    let bundleID = args[1]
    let processName = args[2]
    let opensChatShortcut = args[3] == "yes"
    let prompt = args[4]
    let timeout = TimeInterval(args[5]) ?? 180

    guard CGPreflightPostEventAccess() else {
        _ = CGRequestPostEventAccess()
        throw BridgeFailure(description: "macOS blocked keyboard/mouse control. Enable Accessibility for the app running this command in System Settings > Privacy & Security > Accessibility.")
    }
    guard CGPreflightScreenCaptureAccess() else {
        _ = CGRequestScreenCaptureAccess()
        throw BridgeFailure(description: "macOS blocked reading the app window. Enable Screen Recording for the app running this command in System Settings > Privacy & Security > Screen Recording.")
    }

    guard let app = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).first,
          app.activate(options: [.activateAllWindows]) else {
        throw BridgeFailure(description: "Could not activate \(processName)")
    }
    try await Task.sleep(for: .seconds(1))

    let (_, frame) = try await captureWindow(bundleID: bundleID)
    if opensChatShortcut {
        try postKey(34, flags: [.maskCommand, .maskControl])
        try await Task.sleep(for: .seconds(1))
    } else {
        try postClick(CGPoint(x: frame.midX, y: frame.maxY - min(72, frame.height * 0.1)))
        try await Task.sleep(for: .milliseconds(300))
    }
    let baseline = try await currentText(bundleID: bundleID)

    let pasteboard = NSPasteboard.general
    let savedClipboard = saveClipboard(pasteboard)
    pasteboard.clearContents()
    guard pasteboard.setString(prompt, forType: .string) else {
        restoreClipboard(pasteboard, savedItems: savedClipboard)
        throw BridgeFailure(description: "Could not place the prompt on the macOS clipboard")
    }
    do {
        try postKey(9, flags: [.maskCommand])
    } catch {
        restoreClipboard(pasteboard, savedItems: savedClipboard)
        throw error
    }
    try await Task.sleep(for: .milliseconds(300))
    restoreClipboard(pasteboard, savedItems: savedClipboard)
    try postKey(36)
    try await Task.sleep(for: .seconds(2))

    let deadline = Date().addingTimeInterval(timeout)
    var previous = baseline
    var lastChange = Date()
    var response: [String] = []
    let baselineCounts = baseline.reduce(into: [String: Int]()) { counts, line in
        counts[line, default: 0] += 1
    }
    while Date() < deadline {
        try await Task.sleep(for: .seconds(2))
        let visibleLines = try await currentText(bundleID: bundleID)
        var occurrences: [String: Int] = [:]
        let changedLines = visibleLines.filter { line in
            occurrences[line, default: 0] += 1
            let isNewOccurrence = occurrences[line, default: 0] > baselineCounts[line, default: 0]
            return isNewOccurrence &&
                !line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
                line.trimmingCharacters(in: .whitespacesAndNewlines) != prompt.trimmingCharacters(in: .whitespacesAndNewlines) &&
                (prompt.count < 8 || !line.localizedCaseInsensitiveContains(prompt))
        }
        if visibleLines != previous {
            previous = visibleLines
            lastChange = Date()
            response = changedLines
        }
        if !response.isEmpty && Date().timeIntervalSince(lastChange) >= 8 {
            let result = response.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            if !result.isEmpty {
                print(result)
                return
            }
        }
    }
    throw BridgeFailure(description: "Timed out waiting for readable reply text in \(processName)")
}

Task {
    do {
        try await run()
        exit(EXIT_SUCCESS)
    } catch {
        fputs("\(error)\n", stderr)
        exit(EXIT_FAILURE)
    }
}
dispatchMain()
