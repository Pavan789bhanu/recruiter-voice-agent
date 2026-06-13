import Foundation

// MARK: - Call

struct ActiveCall: Identifiable, Equatable {
    let id: String          // call_sid
    var callerType: CallerType
    var aiActive: Bool
    var turnCount: Int
    var fromNumber: String
    var startedAt: Date

    enum CallerType: String {
        case unknown, ai, human
    }
}

// MARK: - Transcript

struct TranscriptMessage: Identifiable, Equatable {
    let id = UUID()
    let speaker: Speaker
    let text: String
    let timestamp: Date

    enum Speaker: String {
        case recruiter = "Recruiter"
        case candidate = "Candidate (AI)"
    }

    var isCandidate: Bool { speaker == .candidate }
}

// MARK: - Saved Transcript

struct SavedTranscript: Identifiable, Decodable {
    var id: String { filename }
    let filename: String
    let callSid: String
    let turns: Int
    let preview: String

    enum CodingKeys: String, CodingKey {
        case filename, callSid = "call_sid", turns, preview
    }
}

// MARK: - Server Events

enum ServerEvent {
    case connected(callSid: String)
    case transcript(speaker: TranscriptMessage.Speaker, text: String)
    case callerClassified(type: String, confidence: Double, signals: [String])
    case aiToggled(enabled: Bool)
    case unknown
}

extension ServerEvent {
    static func from(json: [String: Any]) -> ServerEvent {
        guard let type = json["type"] as? String else { return .unknown }
        switch type {
        case "connected":
            return .connected(callSid: json["call_sid"] as? String ?? "")
        case "transcript":
            let speakerRaw = json["speaker"] as? String ?? "recruiter"
            let speaker: TranscriptMessage.Speaker = speakerRaw == "candidate"
                ? .candidate : .recruiter
            return .transcript(speaker: speaker, text: json["text"] as? String ?? "")
        case "caller_classified":
            return .callerClassified(
                type: json["type"] as? String ?? "unknown",
                confidence: json["confidence"] as? Double ?? 0,
                signals: json["signals"] as? [String] ?? []
            )
        case "ai_toggled":
            return .aiToggled(enabled: json["enabled"] as? Bool ?? true)
        default:
            return .unknown
        }
    }
}
