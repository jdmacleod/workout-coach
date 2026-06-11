import CoachInferCore
import Foundation
import FoundationModels

// MARK: - Schema builder (I1)

enum SchemaError: Error, LocalizedError {
    case unknownType(String)
    case missingArrayItems

    var errorDescription: String? {
        switch self {
        case .unknownType(let t): return "Unknown schema type '\(t)'"
        case .missingArrayItems: return "Array schema is missing 'items'"
        }
    }
}

func buildDynamicSchema(_ node: SchemaNode) throws -> DynamicGenerationSchema {
    switch node.type {
    case "string":  return DynamicGenerationSchema(type: String.self, guides: [])
    case "integer": return DynamicGenerationSchema(type: Int.self, guides: [])
    case "double":  return DynamicGenerationSchema(type: Double.self, guides: [])
    case "boolean": return DynamicGenerationSchema(type: Bool.self, guides: [])
    case "null":
        if #available(macOS 26.4, *) { return .null }
        throw SchemaError.unknownType("null schema requires macOS 26.4 or later")
    case "object":
        let props = try (node.properties ?? []).map { prop in
            let propSchema = try buildDynamicSchema(prop.schema)
            return DynamicGenerationSchema.Property(
                name: prop.name,
                description: nil,
                schema: propSchema,
                isOptional: prop.isOptional
            )
        }
        return DynamicGenerationSchema(
            name: node.name ?? "Object",
            description: node.description,
            properties: props
        )
    case "array":
        guard let itemNode = node.items else { throw SchemaError.missingArrayItems }
        let itemSchema = try buildDynamicSchema(itemNode)
        return DynamicGenerationSchema(
            arrayOf: itemSchema,
            minimumElements: node.min,
            maximumElements: node.max
        )
    default:
        throw SchemaError.unknownType(node.type)
    }
}

// MARK: - Entry point

let inputData = FileHandle.standardInput.readDataToEndOfFile()
let request = try JSONDecoder().decode(Request.self, from: inputData)

let session = LanguageModelSession(instructions: request.system)
let opts = GenerationOptions(maximumResponseTokens: request.maxTokens)

do {  // I3: catch all model errors and return them as a structured error response
    let text: String
    if let schemaNode = request.schema {  // I1: structured generation path
        let dynSchema = try buildDynamicSchema(schemaNode)
        let genSchema = try GenerationSchema(root: dynSchema, dependencies: [])
        let result = try await session.respond(
            to: request.user,
            schema: genSchema,
            includeSchemaInPrompt: false,
            options: opts
        )
        text = result.content.jsonString
    } else {
        let result = try await session.respond(to: request.user, options: opts)
        text = result.content
    }
    let response = Response(text: text, model: "apple/on-device")
    FileHandle.standardOutput.write(try JSONEncoder().encode(response))
} catch {
    let errResp = Response(text: "", model: "apple/on-device", error: error.localizedDescription)
    if let data = try? JSONEncoder().encode(errResp) {
        FileHandle.standardOutput.write(data)
    }
}
