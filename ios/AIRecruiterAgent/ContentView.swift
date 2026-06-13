import SwiftUI

struct ContentView: View {
    @EnvironmentObject var callManager: CallManager
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            DashboardView()
                .tabItem {
                    Label("Dashboard", systemImage: "phone.fill")
                }
                .tag(0)

            TranscriptsView()
                .tabItem {
                    Label("History", systemImage: "clock.fill")
                }
                .tag(1)

            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape.fill")
                }
                .tag(2)
        }
        .onAppear { callManager.startPolling() }
    }
}

// MARK: - Dashboard

struct DashboardView: View {
    @EnvironmentObject var callManager: CallManager

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Server status bar
                ServerStatusBar(online: callManager.serverOnline)

                if callManager.activeCalls.isEmpty {
                    IdleView()
                } else {
                    List(callManager.activeCalls) { call in
                        NavigationLink(destination: LiveCallView(call: call)) {
                            ActiveCallRow(call: call)
                        }
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle("AI Recruiter Agent")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { Task { await callManager.refreshActiveCalls() } }) {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
        }
    }
}

struct ServerStatusBar: View {
    let online: Bool
    var body: some View {
        HStack {
            Circle()
                .fill(online ? Color.green : Color.red)
                .frame(width: 8, height: 8)
            Text(online ? "Server Connected" : "Server Offline")
                .font(.caption)
                .foregroundColor(.secondary)
            Spacer()
            Text("Twilio Number Active")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color(.systemGroupedBackground))
    }
}

struct IdleView: View {
    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "phone.badge.checkmark")
                .font(.system(size: 64))
                .foregroundColor(.green)
            Text("Ready to Answer Calls")
                .font(.title2.bold())
            Text("When a recruiter calls your Twilio number,\nthe AI will handle it automatically.\nYou'll see live call details here.")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
                .padding(.horizontal, 40)
            Spacer()
        }
    }
}

struct ActiveCallRow: View {
    let call: ActiveCall

    var callerTypeColor: Color {
        switch call.callerType {
        case .ai:     return .blue
        case .human:  return .orange
        case .unknown: return .gray
        }
    }

    var callerTypeLabel: String {
        switch call.callerType {
        case .ai:      return "AI Recruiter"
        case .human:   return "Human Recruiter"
        case .unknown: return "Analyzing..."
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            // Animated indicator
            ZStack {
                Circle()
                    .fill(callerTypeColor.opacity(0.15))
                    .frame(width: 50, height: 50)
                Image(systemName: call.callerType == .human ? "person.fill" : "cpu")
                    .foregroundColor(callerTypeColor)
                    .font(.title3)
            }

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(callerTypeLabel)
                        .font(.headline)
                    Spacer()
                    // AI active badge
                    if call.callerType == .ai {
                        Label(call.aiActive ? "AI ON" : "AI OFF", systemImage: "sparkles")
                            .font(.caption2.bold())
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(call.aiActive ? Color.blue.opacity(0.15) : Color.gray.opacity(0.15))
                            .foregroundColor(call.aiActive ? .blue : .gray)
                            .clipShape(Capsule())
                    }
                }
                Text("\(call.turnCount) exchange\(call.turnCount == 1 ? "" : "s")")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 6)
    }
}

// MARK: - Live Call View

struct LiveCallView: View {
    let call: ActiveCall
    @StateObject private var wsManager = CallWebSocketManager()
    @State private var messages: [TranscriptMessage] = []
    @State private var aiEnabled: Bool = true
    @State private var callerType: String = "Analyzing..."
    @State private var callerConfidence: Double = 0
    @EnvironmentObject var callManager: CallManager

    var body: some View {
        VStack(spacing: 0) {
            // Caller type badge
            CallerTypeBanner(type: callerType, confidence: callerConfidence)

            // Live transcript
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(messages) { msg in
                            TranscriptBubble(message: msg)
                                .id(msg.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: messages.count) { _ in
                    if let last = messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }

            Divider()

            // Controls
            HStack(spacing: 20) {
                Toggle(isOn: $aiEnabled) {
                    Label("AI Responding", systemImage: "sparkles")
                        .font(.subheadline.bold())
                }
                .toggleStyle(SwitchToggleStyle(tint: .blue))
                .onChange(of: aiEnabled) { enabled in
                    wsManager.toggleAI(enabled: enabled)
                    Task { await callManager.toggleAI(for: call, enabled: enabled) }
                }
            }
            .padding()
            .background(Color(.systemGroupedBackground))
        }
        .navigationTitle("Live Call")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            aiEnabled = call.aiActive
            wsManager.connect(callSid: call.id)
            wsManager.onEvent = { event in
                handleEvent(event)
            }
        }
        .onDisappear { wsManager.disconnect() }
    }

    private func handleEvent(_ event: ServerEvent) {
        switch event {
        case .transcript(let speaker, let text):
            messages.append(TranscriptMessage(speaker: speaker, text: text, timestamp: Date()))
        case .callerClassified(let type, let confidence, _):
            callerType = type == "ai" ? "AI Recruiter Detected" : "Human Recruiter Detected"
            callerConfidence = confidence
        case .aiToggled(let enabled):
            aiEnabled = enabled
        default:
            break
        }
    }
}

struct CallerTypeBanner: View {
    let type: String
    let confidence: Double

    var isAI: Bool { type.contains("AI") }

    var body: some View {
        HStack {
            Image(systemName: isAI ? "cpu" : "person.fill")
            Text(type)
                .font(.subheadline.bold())
            Spacer()
            if confidence > 0 {
                Text("\(Int(confidence * 100))% confident")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .background(isAI ? Color.blue.opacity(0.1) : Color.orange.opacity(0.1))
        .foregroundColor(isAI ? .blue : .orange)
    }
}

struct TranscriptBubble: View {
    let message: TranscriptMessage

    var body: some View {
        HStack {
            if message.isCandidate { Spacer(minLength: 60) }
            VStack(alignment: message.isCandidate ? .trailing : .leading, spacing: 4) {
                Text(message.speaker.rawValue)
                    .font(.caption2.bold())
                    .foregroundColor(.secondary)
                Text(message.text)
                    .padding(12)
                    .background(message.isCandidate ? Color.blue : Color(.systemGray5))
                    .foregroundColor(message.isCandidate ? .white : .primary)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                Text(message.timestamp, style: .time)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            if !message.isCandidate { Spacer(minLength: 60) }
        }
    }
}

// MARK: - Transcripts History

struct TranscriptsView: View {
    @State private var transcripts: [SavedTranscript] = []
    @State private var loading = false

    var body: some View {
        NavigationStack {
            Group {
                if loading {
                    ProgressView("Loading history...")
                } else if transcripts.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "clock.badge.xmark")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        Text("No call history yet")
                            .foregroundColor(.secondary)
                    }
                } else {
                    List(transcripts) { transcript in
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Call: \(transcript.callSid.prefix(8))...")
                                .font(.headline)
                            Text(transcript.preview)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(2)
                            Text("\(transcript.turns) exchanges")
                                .font(.caption2)
                                .foregroundColor(.blue)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
            .navigationTitle("Call History")
            .task { await loadTranscripts() }
        }
    }

    func loadTranscripts() async {
        loading = true
        transcripts = (try? await BackendAPI.shared.fetchTranscripts()) ?? []
        loading = false
    }
}

// MARK: - Settings

struct SettingsView: View {
    @AppStorage("serverURL") private var serverURL = "https://YOUR_SERVER_URL"
    @State private var isTestingConnection = false
    @State private var connectionStatus = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Server Configuration") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Backend URL")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        TextField("https://your-server.com", text: $serverURL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                            .onChange(of: serverURL) { url in
                                BackendAPI.shared.baseURL = url
                            }
                    }

                    Button {
                        Task { await testConnection() }
                    } label: {
                        HStack {
                            if isTestingConnection {
                                ProgressView().scaleEffect(0.8)
                            } else {
                                Image(systemName: "network")
                            }
                            Text("Test Connection")
                        }
                    }
                    .disabled(isTestingConnection)

                    if !connectionStatus.isEmpty {
                        Text(connectionStatus)
                            .font(.caption)
                            .foregroundColor(connectionStatus.contains("✓") ? .green : .red)
                    }
                }

                Section("Twilio Number") {
                    HStack {
                        Image(systemName: "phone.fill")
                            .foregroundColor(.green)
                        Text("Share this number with recruiters")
                            .font(.subheadline)
                    }
                    Text("Configure in Twilio Dashboard")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Section("How It Works") {
                    VStack(alignment: .leading, spacing: 8) {
                        InfoRow(icon: "1.circle.fill", color: .blue,
                                title: "Recruiter calls your Twilio number")
                        InfoRow(icon: "2.circle.fill", color: .blue,
                                title: "AI detects if caller is AI or human")
                        InfoRow(icon: "3.circle.fill", color: .blue,
                                title: "If AI: Claude answers using your resume")
                        InfoRow(icon: "4.circle.fill", color: .orange,
                                title: "If Human: you get a push notification")
                    }
                    .padding(.vertical, 4)
                }
            }
            .navigationTitle("Settings")
        }
    }

    func testConnection() async {
        isTestingConnection = true
        connectionStatus = ""
        BackendAPI.shared.baseURL = serverURL
        let ok = await BackendAPI.shared.healthCheck()
        connectionStatus = ok ? "✓ Connected successfully" : "✗ Cannot reach server"
        isTestingConnection = false
    }
}

struct InfoRow: View {
    let icon: String
    let color: Color
    let title: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .foregroundColor(color)
            Text(title)
                .font(.caption)
        }
    }
}
