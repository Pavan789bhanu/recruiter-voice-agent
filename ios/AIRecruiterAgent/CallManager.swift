import Foundation
import Combine

// MARK: - CallManager (global app state)

@MainActor
final class CallManager: ObservableObject {
    @Published var activeCalls: [ActiveCall] = []
    @Published var serverOnline = false
    @Published var isPolling = false

    private var pollingTask: Task<Void, Never>?

    func startPolling() {
        guard !isPolling else { return }
        isPolling = true
        pollingTask = Task {
            while !Task.isCancelled {
                await refreshActiveCalls()
                await checkServerHealth()
                try? await Task.sleep(nanoseconds: 3_000_000_000)  // every 3s
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        isPolling = false
    }

    func refreshActiveCalls() async {
        guard let calls = try? await BackendAPI.shared.fetchActiveCalls() else { return }
        activeCalls = calls
    }

    func checkServerHealth() async {
        serverOnline = await BackendAPI.shared.healthCheck()
    }

    func toggleAI(for call: ActiveCall, enabled: Bool) async {
        try? await BackendAPI.shared.toggleAI(callSid: call.id, enabled: enabled)
        if let idx = activeCalls.firstIndex(where: { $0.id == call.id }) {
            activeCalls[idx].aiActive = enabled
        }
    }
}
