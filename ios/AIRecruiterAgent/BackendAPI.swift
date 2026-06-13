import Foundation

// MARK: - Backend API Client

final class BackendAPI {
    static let shared = BackendAPI()

    // Set this to your EC2 public URL (same as PUBLIC_URL in .env)
    var baseURL = UserDefaults.standard.string(forKey: "serverURL") ?? "https://YOUR_SERVER_URL"

    private let session = URLSession.shared

    // MARK: - Device Registration

    func registerDevice(pushToken: String) async {
        guard let url = URL(string: "\(baseURL)/api/register-device") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let deviceId = UIDevice.current.identifierForVendor?.uuidString ?? UUID().uuidString
        let body = ["device_id": deviceId, "push_token": pushToken]
        request.httpBody = try? JSONEncoder().encode(body)

        _ = try? await session.data(for: request)
    }

    // MARK: - Active Calls

    func fetchActiveCalls() async throws -> [ActiveCall] {
        let url = URL(string: "\(baseURL)/api/active-calls")!
        let (data, _) = try await session.data(from: url)
        struct Response: Decodable {
            struct Call: Decodable {
                let call_sid: String
                let turn_count: Int
                let caller_type: String?
                let ai_active: Bool
            }
            let calls: [Call]
        }
        let resp = try JSONDecoder().decode(Response.self, from: data)
        return resp.calls.map {
            ActiveCall(
                id: $0.call_sid,
                callerType: ActiveCall.CallerType(rawValue: $0.caller_type ?? "unknown") ?? .unknown,
                aiActive: $0.ai_active,
                turnCount: $0.turn_count,
                fromNumber: "Unknown",
                startedAt: Date()
            )
        }
    }

    // MARK: - Toggle AI

    func toggleAI(callSid: String, enabled: Bool) async throws {
        let url = URL(string: "\(baseURL)/api/toggle-ai")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = ["call_sid": callSid, "enabled": enabled] as [String: Any]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        _ = try? await session.data(for: request)
    }

    // MARK: - Transcripts

    func fetchTranscripts() async throws -> [SavedTranscript] {
        let url = URL(string: "\(baseURL)/api/transcripts")!
        let (data, _) = try await session.data(from: url)
        struct Response: Decodable {
            let transcripts: [SavedTranscript]
        }
        return try JSONDecoder().decode(Response.self, from: data).transcripts
    }

    // MARK: - Health Check

    func healthCheck() async -> Bool {
        guard let url = URL(string: "\(baseURL)/health") else { return false }
        guard let (_, response) = try? await session.data(from: url) else { return false }
        return (response as? HTTPURLResponse)?.statusCode == 200
    }
}

// MARK: - WebSocket Manager (per-call live updates)

final class CallWebSocketManager: NSObject, ObservableObject, URLSessionWebSocketDelegate {
    private var webSocketTask: URLSessionWebSocketTask?
    var onEvent: ((ServerEvent) -> Void)?

    func connect(callSid: String) {
        let urlString = BackendAPI.shared.baseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
        guard let url = URL(string: "\(urlString)/ws/app/\(callSid)") else { return }

        let session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        receive()
    }

    func disconnect() {
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
    }

    func toggleAI(enabled: Bool) {
        let msg = ["action": "toggle_ai", "enabled": enabled] as [String: Any]
        guard let data = try? JSONSerialization.data(withJSONObject: msg),
              let str = String(data: data, encoding: .utf8) else { return }
        webSocketTask?.send(.string(str)) { _ in }
    }

    private func receive() {
        webSocketTask?.receive { [weak self] result in
            switch result {
            case .success(let message):
                if case .string(let text) = message,
                   let data = text.data(using: .utf8),
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    let event = ServerEvent.from(json: json)
                    DispatchQueue.main.async {
                        self?.onEvent?(event)
                    }
                }
                self?.receive()
            case .failure:
                break
            }
        }
    }
}
