import SwiftUI

struct ReviewView: View {
    private enum Phase {
        case loading
        case empty
        case question(DueCard)
        case grading(DueCard)
        case graded(DueCard, AnswerResult)
        case error(String)
    }

    @State private var phase: Phase = .loading
    @State private var queue: [DueCard] = []
    @State private var index = 0
    @State private var answerText = ""

    var body: some View {
        NavigationStack {
            Group {
                switch phase {
                case .loading:
                    ProgressView("Loading due cards…")
                case .empty:
                    ContentUnavailableView("No cards due 🎉", systemImage: "checkmark.circle",
                                           description: Text("Come back later, or approve new imports in your inbox."))
                case .question(let card):
                    questionView(card)
                case .grading:
                    ProgressView("Grading your answer…")
                case .graded(_, let result):
                    resultView(result)
                case .error(let message):
                    ContentUnavailableView("Something went wrong", systemImage: "exclamationmark.triangle",
                                           description: Text(message))
                }
            }
            .navigationTitle("Review\(queue.isEmpty ? "" : " (\(max(queue.count - index, 0)) due)")")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                Button("Reload") { Task { await load() } }
            }
            .task { await load() }
        }
    }

    private func questionView(_ card: DueCard) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let title = card.sourceTitle {
                    Text(title).font(.caption).foregroundStyle(.secondary)
                }
                Text(card.question).font(.headline)
                TextEditor(text: $answerText)
                    .frame(minHeight: 120)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
                Button("Submit") { Task { await submit(card) } }
                    .buttonStyle(.borderedProminent)
                    .disabled(answerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding()
        }
    }

    private func resultView(_ result: AnswerResult) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text(result.grade.capitalized)
                    .font(.title2).bold()
                    .foregroundStyle(gradeColor(result.grade))
                Text(result.feedback)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Full answer").font(.caption).foregroundStyle(.secondary)
                    Text(result.correctAnswer).font(.callout)
                }
                Button("Next") { advance() }
                    .buttonStyle(.borderedProminent)
            }
            .padding()
        }
    }

    private func gradeColor(_ grade: String) -> Color {
        switch grade {
        case "good", "easy": return .green
        case "hard": return .orange
        default: return .red
        }
    }

    private func load() async {
        phase = .loading
        do {
            queue = try await API.dueCards()
            index = 0
            answerText = ""
            phase = queue.isEmpty ? .empty : .question(queue[0])
        } catch {
            phase = .error(error.localizedDescription)
        }
    }

    private func submit(_ card: DueCard) async {
        phase = .grading(card)
        do {
            let result = try await API.answer(cardId: card.id, text: answerText)
            phase = .graded(card, result)
        } catch {
            phase = .error(error.localizedDescription)
        }
    }

    private func advance() {
        index += 1
        answerText = ""
        phase = index < queue.count ? .question(queue[index]) : .empty
    }
}
