import Foundation

enum APIError: LocalizedError {
    case http(Int, String)

    var errorDescription: String? {
        switch self {
        case .http(let code, let detail): return "Server error \(code): \(detail)"
        }
    }
}

struct InboxCard: Codable, Identifiable, Hashable {
    let id: Int
    let question: String
    let answer: String
}

struct InboxSource: Codable, Identifiable, Hashable {
    let id: Int
    let url: String
    let sourceType: String
    let title: String?
    let status: String
    let triageReason: String?
    let cards: [InboxCard]
}

struct CaptureResponse: Codable {
    let id: Int
    let status: String
}

struct SourceStatus: Codable {
    let id: Int
    let status: String
    let progress: Int
    let title: String?
    let triageReason: String?
    let cardCount: Int
}

struct DueCard: Codable, Identifiable, Hashable {
    let id: Int
    let question: String
    let sourceTitle: String?
    let dueAt: String
}

struct AnswerResult: Codable {
    let grade: String
    let feedback: String
    let correctAnswer: String
    let nextDue: String
}

struct ManagedCard: Codable, Identifiable, Hashable {
    let id: Int
    let question: String
    let answer: String
    let status: String
    let suspended: Bool
    let dueAt: String?
    let sourceTitle: String?
    let sourceType: String
}

struct API {
    static let baseURL = URL(string: "https://app-production-1e43.up.railway.app")!

    private static var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private static func request<T: Decodable>(_ type: T.Type, path: String, method: String = "GET",
                                              body: [String: Any]? = nil) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = method
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await URLSession.shared.data(for: req)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            throw APIError.http(code, String(data: data, encoding: .utf8) ?? "")
        }
        return try decoder.decode(T.self, from: data)
    }

    static func capture(url: String) async throws -> CaptureResponse {
        try await request(CaptureResponse.self, path: "capture", method: "POST", body: ["url": url])
    }

    static func sourceStatus(id: Int) async throws -> SourceStatus {
        try await request(SourceStatus.self, path: "sources/\(id)")
    }

    static func inbox() async throws -> [InboxSource] {
        try await request([InboxSource].self, path: "inbox")
    }

    static func approve(sourceId: Int) async throws -> InboxSource {
        try await request(InboxSource.self, path: "sources/\(sourceId)/approve", method: "POST")
    }

    static func reject(sourceId: Int) async throws -> InboxSource {
        try await request(InboxSource.self, path: "sources/\(sourceId)/reject", method: "POST")
    }

    static func dueCards() async throws -> [DueCard] {
        try await request([DueCard].self, path: "review/due")
    }

    static func answer(cardId: Int, text: String) async throws -> AnswerResult {
        try await request(AnswerResult.self, path: "review/\(cardId)/answer", method: "POST",
                          body: ["answer": text])
    }

    static func allCards() async throws -> [ManagedCard] {
        try await request([ManagedCard].self, path: "cards")
    }

    struct UpdatedCard: Codable {
        let id: Int
        let status: String
        let suspended: Bool
    }

    static func updateCard(id: Int, question: String? = nil, answer: String? = nil,
                           suspended: Bool? = nil) async throws -> UpdatedCard {
        var body: [String: Any] = [:]
        if let question { body["question"] = question }
        if let answer { body["answer"] = answer }
        if let suspended { body["suspended"] = suspended }
        return try await request(UpdatedCard.self, path: "cards/\(id)", method: "PATCH", body: body)
    }

    struct Deleted: Codable { let deleted: Int }

    @discardableResult
    static func deleteCard(id: Int) async throws -> Deleted {
        try await request(Deleted.self, path: "cards/\(id)", method: "DELETE")
    }
}
