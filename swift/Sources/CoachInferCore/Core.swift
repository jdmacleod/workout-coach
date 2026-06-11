// Pure-logic types shared between CoachInfer and the test suite.
// No FoundationModels dependency — compiles without Apple Intelligence.
import Foundation

// MARK: - SchemaNode

/// Tree node for the schema wire format sent from Python to request structured generation.
/// Kept in CoachInferCore so tests can decode/verify without a FoundationModels dependency.
public final class SchemaNode: Decodable, Sendable {
    /// Leaf types: "string" | "integer" | "double" | "boolean" | "null"
    /// Composite types: "object" | "array"
    public let type: String
    public let name: String?            // required for "object"
    public let description: String?     // optional description for "object"
    public let properties: [SchemaProperty]?  // "object" fields
    public let items: SchemaNode?       // "array" element schema (class allows self-reference)
    public let min: Int?                // "array" minimumElements
    public let max: Int?                // "array" maximumElements

    enum CodingKeys: String, CodingKey {
        case type, name, description, properties, items, min, max
    }
}

/// A named property within an object schema node.
public struct SchemaProperty: Decodable, Sendable {
    public let name: String
    public let schema: SchemaNode
    public let isOptional: Bool

    enum CodingKeys: String, CodingKey {
        case name, schema
        case isOptional = "is_optional"
    }
}

// MARK: - Request

/// JSON payload received on stdin.
public struct Request: Decodable, Sendable {
    public let system: String
    public let user: String
    public let maxTokens: Int
    /// When present, the executable uses guided generation via DynamicGenerationSchema.
    /// When nil, the response is free-form text.
    public let schema: SchemaNode?

    public init(system: String, user: String, maxTokens: Int, schema: SchemaNode? = nil) {
        self.system = system
        self.user = user
        self.maxTokens = maxTokens
        self.schema = schema
    }

    enum CodingKeys: String, CodingKey {
        case system, user, schema
        case maxTokens = "max_tokens"
    }
}

// MARK: - Response

/// JSON payload written to stdout.
public struct Response: Codable, Sendable {
    public let text: String
    public let model: String
    /// Non-nil when inference fails. Python raises InferenceError when this field is present.
    public let error: String?

    public init(text: String, model: String, error: String? = nil) {
        self.text = text
        self.model = model
        self.error = error
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(text, forKey: .text)
        try c.encode(model, forKey: .model)
        try c.encodeIfPresent(error, forKey: .error)  // omit key when nil
    }
}
