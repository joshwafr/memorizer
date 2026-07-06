import SwiftUI

struct VoiceView: View {
    @StateObject private var session = VoiceSession()

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Spacer()
                statusView
                Spacer()
                controls
            }
            .padding()
            .navigationTitle("Voice session")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    @ViewBuilder
    private var statusView: some View {
        switch session.state {
        case .idle:
            VStack(spacing: 12) {
                Image(systemName: "headphones")
                    .font(.system(size: 56))
                    .foregroundStyle(.secondary)
                Text("Pop in your AirPods and start a hands-free review.")
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
            }
        case .starting:
            ProgressView("Loading your due cards…")
        case .speakingQuestion:
            phaseView(icon: "speaker.wave.2.fill", tint: .blue,
                      title: currentCounter, detail: currentQuestion)
        case .listening:
            VStack(spacing: 14) {
                phaseView(icon: "mic.fill", tint: .red,
                          title: "Listening…", detail: currentQuestion)
                Text(session.liveTranscript.isEmpty ? "Say your answer" : session.liveTranscript)
                    .font(.body.italic())
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
                    .background(RoundedRectangle(cornerRadius: 10).fill(.quaternary.opacity(0.5)))
            }
        case .grading:
            ProgressView("Grading your answer…")
        case .speakingFeedback:
            if let result = session.lastResult {
                VStack(spacing: 10) {
                    Text(result.grade.capitalized)
                        .font(.title).bold()
                        .foregroundStyle(gradeColor(result.grade))
                    Text(result.feedback)
                        .multilineTextAlignment(.leading)
                        .foregroundStyle(.secondary)
                }
            } else {
                ProgressView()
            }
        case .finished:
            VStack(spacing: 12) {
                Image(systemName: "checkmark.seal.fill")
                    .font(.system(size: 56))
                    .foregroundStyle(.green)
                Text("Session complete 🎉").font(.headline)
            }
        case .error(let message):
            ContentUnavailableView("Can't start", systemImage: "exclamationmark.triangle",
                                   description: Text(message))
        }
    }

    private var currentCounter: String {
        "Card \(min(session.index + 1, max(session.queue.count, 1))) of \(session.queue.count)"
    }

    private var currentQuestion: String {
        session.index < session.queue.count ? session.queue[session.index].question : ""
    }

    private func phaseView(icon: String, tint: Color, title: String, detail: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: icon).font(.system(size: 44)).foregroundStyle(tint)
            Text(title).font(.headline)
            Text(detail)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.leading)
        }
    }

    private func gradeColor(_ grade: String) -> Color {
        switch grade {
        case "good", "easy": return .green
        case "hard": return .orange
        default: return .red
        }
    }

    @ViewBuilder
    private var controls: some View {
        switch session.state {
        case .idle, .finished, .error:
            Button {
                Task { await session.start() }
            } label: {
                Label("Start session", systemImage: "play.fill")
                    .font(.title3.bold())
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
            }
            .buttonStyle(.borderedProminent)
        default:
            VStack(spacing: 10) {
                if session.state == .listening {
                    Button {
                        session.finishAnswer()
                    } label: {
                        Label("Done answering", systemImage: "checkmark")
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                    }
                    .buttonStyle(.borderedProminent)
                }
                HStack {
                    Button("Skip card") { session.skipCard() }
                        .buttonStyle(.bordered)
                    Button("End session", role: .destructive) { session.stop() }
                        .buttonStyle(.bordered)
                }
            }
        }
    }
}
