import SwiftUI

struct HomeView: View {
    @State private var urlText = ""
    @State private var captureMessage: String?
    @State private var progress: Int?
    @State private var progressLabel = ""
    @State private var inbox: [InboxSource] = []
    @State private var loadError: String?
    @State private var busySourceIds: Set<Int> = []

    var body: some View {
        NavigationStack {
            List {
                Section("Capture") {
                    HStack {
                        TextField("Paste a YouTube or article link…", text: $urlText)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                        Button("Capture") { Task { await capture() } }
                            .buttonStyle(.borderedProminent)
                            .disabled(urlText.isEmpty)
                    }
                    if let progress {
                        VStack(alignment: .leading, spacing: 6) {
                            ProgressView(value: Double(progress), total: 100)
                            Text("\(progress)% — \(progressLabel)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    if let captureMessage {
                        Text(captureMessage).font(.callout)
                    }
                }

                Section("Inbox (\(inbox.count))") {
                    if inbox.isEmpty {
                        Text("Inbox empty — capture something above.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(inbox) { source in
                        InboxRow(source: source,
                                 busy: busySourceIds.contains(source.id),
                                 onApprove: { Task { await act(source, approve: true) } },
                                 onReject: { Task { await act(source, approve: false) } })
                    }
                }

                if let loadError {
                    Text(loadError).foregroundStyle(.red).font(.caption)
                }
            }
            .navigationTitle("🧠 Memorizer")
            .refreshable { await loadInbox() }
            .task { await loadInbox() }
        }
    }

    private func loadInbox() async {
        do {
            inbox = try await API.inbox()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func capture() async {
        captureMessage = nil
        progress = 5
        progressLabel = "Starting…"
        do {
            let created = try await API.capture(url: urlText)
            urlText = ""
            var shown = 5
            while true {
                try await Task.sleep(nanoseconds: 1_500_000_000)
                let status = try await API.sourceStatus(id: created.id)
                if status.progress < 100 {
                    shown = min(max(status.progress, shown + 2), 95)
                    progress = shown
                    progressLabel = status.status == "pending"
                        ? "Fetching the content…" : "Reading it and distilling insights…"
                    continue
                }
                progress = nil
                switch status.status {
                case "inbox":
                    captureMessage = "✅ \(status.title ?? "Captured") — \(status.cardCount) cards in your inbox."
                case "discarded":
                    captureMessage = "🗑 Filtered out: \(status.triageReason ?? "not relevant")"
                case "failed":
                    captureMessage = "❌ Failed to process — capture the link again to retry."
                default:
                    captureMessage = "Finished: \(status.status)"
                }
                await loadInbox()
                return
            }
        } catch {
            progress = nil
            captureMessage = "Error: \(error.localizedDescription)"
        }
    }

    private func act(_ source: InboxSource, approve: Bool) async {
        busySourceIds.insert(source.id)
        defer { busySourceIds.remove(source.id) }
        do {
            if approve {
                _ = try await API.approve(sourceId: source.id)
            } else {
                _ = try await API.reject(sourceId: source.id)
            }
            await loadInbox()
        } catch {
            loadError = error.localizedDescription
        }
    }
}

private struct InboxRow: View {
    let source: InboxSource
    let busy: Bool
    let onApprove: () -> Void
    let onReject: () -> Void

    var body: some View {
        DisclosureGroup {
            if let reason = source.triageReason, !reason.isEmpty {
                Text(reason).font(.caption).foregroundStyle(.secondary)
            }
            ForEach(source.cards) { card in
                VStack(alignment: .leading, spacing: 6) {
                    Text(card.question).font(.subheadline).bold()
                    Text(card.answer).font(.caption).foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
            }
            HStack {
                Button("Approve — start learning", action: onApprove)
                    .buttonStyle(.borderedProminent)
                    .tint(.green)
                Button("Reject", role: .destructive, action: onReject)
                    .buttonStyle(.bordered)
            }
            .disabled(busy)
        } label: {
            HStack {
                Text(source.sourceType == "youtube" ? "▶️" : "📰")
                Text(source.title ?? source.url).lineLimit(2).font(.subheadline)
                Spacer()
                Text("\(source.cards.count)")
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(Capsule().fill(Color.accentColor.opacity(0.15)))
            }
        }
    }
}
