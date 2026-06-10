import Foundation
import FoundationModels

struct Request: Decodable {
    let system: String
    let user: String
    let maxTokens: Int

    enum CodingKeys: String, CodingKey {
        case system, user
        case maxTokens = "max_tokens"
    }
}

struct Response: Encodable {
    let text: String
    let model: String
}

let inputData = FileHandle.standardInput.readDataToEndOfFile()
let request = try JSONDecoder().decode(Request.self, from: inputData)

let session = LanguageModelSession(instructions: request.system)
let result = try await session.respond(
    to: request.user,
    options: GenerationOptions(maximumResponseTokens: request.maxTokens)
)

let response = Response(text: result.content, model: "apple/on-device")
FileHandle.standardOutput.write(try JSONEncoder().encode(response))
