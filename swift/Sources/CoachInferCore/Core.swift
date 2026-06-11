// Pure-logic types shared between CoachInfer and the test suite.
// No FoundationModels dependency — compiles without Apple Intelligence.
import Foundation

// MARK: - Request

/// JSON payload received on stdin.
public struct Request: Decodable, Sendable {
    public let system: String
    public let user: String
    public let maxTokens: Int

    public init(system: String, user: String, maxTokens: Int) {
        self.system = system
        self.user = user
        self.maxTokens = maxTokens
    }

    enum CodingKeys: String, CodingKey {
        case system, user
        case maxTokens = "max_tokens"
    }
}

// MARK: - Response

/// JSON payload written to stdout.
public struct Response: Encodable, Sendable {
    public let text: String
    public let model: String

    public init(text: String, model: String) {
        self.text = text
        self.model = model
    }
}
