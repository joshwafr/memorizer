import SwiftUI

struct CardsView: View {
    @State private var cards: [ManagedCard] = []
    @State private var filter = "all"
    @State private var editing: ManagedCard?
    @State private var loadError: String?

    private let filters = ["all", "learning", "inbox", "suspended", "inactive"]

    private var visible: [ManagedCard] {
        filter == "all" ? cards : cards.filter { $0.status == filter }
    }

    var body: some View {
        NavigationStack {
            List {
                Picker("Filter", selection: $filter) {
                    ForEach(filters, id: \.self) { Text($0.capitalized).tag($0) }
                }
                .pickerStyle(.menu)

                if let loadError {
                    Text(loadError).foregroundStyle(.red).font(.caption)
                }

                ForEach(visible) { card in
                    Button {
                        editing = card
                    } label: {
                        CardRow(card: card)
                    }
                    .foregroundStyle(.primary)
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) {
                            Task { await delete(card) }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        Button {
                            Task { await toggleSuspend(card) }
                        } label: {
                            Label(card.suspended ? "Resume" : "Suspend",
                                  systemImage: card.suspended ? "play" : "pause")
                        }
                        .tint(.orange)
                    }
                }
            }
            .navigationTitle("Cards (\(visible.count))")
            .refreshable { await load() }
            .task { await load() }
            .sheet(item: $editing) { card in
                CardEditView(card: card) { await load() }
            }
        }
    }

    private func load() async {
        do {
            cards = try await API.allCards()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func delete(_ card: ManagedCard) async {
        do {
            try await API.deleteCard(id: card.id)
            await load()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func toggleSuspend(_ card: ManagedCard) async {
        do {
            _ = try await API.updateCard(id: card.id, suspended: !card.suspended)
            await load()
        } catch {
            loadError = error.localizedDescription
        }
    }
}

private struct CardRow: View {
    let card: ManagedCard

    var statusColor: Color {
        switch card.status {
        case "learning": return .green
        case "inbox": return .blue
        case "suspended": return .orange
        default: return .gray
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(card.status)
                    .font(.caption2)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(Capsule().fill(statusColor.opacity(0.15)))
                    .foregroundStyle(statusColor)
                Spacer()
                if !card.suspended, let due = card.dueAt {
                    Text(Self.dueLabel(due)).font(.caption2).foregroundStyle(.secondary)
                }
            }
            Text(card.question).font(.subheadline).lineLimit(2)
            if let title = card.sourceTitle {
                Text("\(card.sourceType == "youtube" ? "▶️" : "📰") \(title)")
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .padding(.vertical, 2)
    }

    static func dueLabel(_ iso: String) -> String {
        guard let date = ISO8601DateFormatter().date(from: iso) else { return "" }
        let days = Int((date.timeIntervalSinceNow / 86400).rounded())
        if days <= 0 { return "due now" }
        if days == 1 { return "due tomorrow" }
        return "due in \(days) days"
    }
}

private struct CardEditView: View {
    let card: ManagedCard
    let onDone: () async -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var question: String
    @State private var answer: String
    @State private var saving = false
    @State private var errorMessage: String?

    init(card: ManagedCard, onDone: @escaping () async -> Void) {
        self.card = card
        self.onDone = onDone
        _question = State(initialValue: card.question)
        _answer = State(initialValue: card.answer)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Question") {
                    TextEditor(text: $question).frame(minHeight: 90)
                }
                Section("Answer") {
                    TextEditor(text: $answer).frame(minHeight: 140)
                }
                if let errorMessage {
                    Text(errorMessage).foregroundStyle(.red).font(.caption)
                }
            }
            .navigationTitle("Edit card")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "Saving…" : "Save") { Task { await save() } }
                        .disabled(saving)
                }
            }
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        do {
            _ = try await API.updateCard(id: card.id, question: question, answer: answer)
            await onDone()
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
