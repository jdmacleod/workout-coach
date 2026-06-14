import CoachInferCore
import Foundation
import FoundationModels

// MARK: - Web search tool

/// Searches the web for exercise information and example workouts.
/// Providers are tried in priority order: Brave Search → Exa → Tavily → DuckDuckGo.
struct WebSearchTool: Tool {
    let searchApiKeys: [String: String]

    var description: String {
        "Search the web for exercise information, workout examples, and movement descriptions " +
        "matching the user's available equipment and goals."
    }

    @Generable
    struct Arguments {
        @Guide(description: "Specific search query about exercises, workout patterns, or equipment")
        var query: String
    }

    func call(arguments: Arguments) async throws -> String {
        if let key = searchApiKeys["brave_search_api_key"], !key.isEmpty,
           let result = try? await searchBrave(query: arguments.query, apiKey: key),
           !result.isEmpty { return result }

        if let key = searchApiKeys["exa_api_key"], !key.isEmpty,
           let result = try? await searchExa(query: arguments.query, apiKey: key),
           !result.isEmpty { return result }

        if let key = searchApiKeys["tavily_api_key"], !key.isEmpty,
           let result = try? await searchTavily(query: arguments.query, apiKey: key),
           !result.isEmpty { return result }

        if let result = try? await searchDuckDuckGo(query: arguments.query),
           !result.isEmpty { return result }

        return "No search results for: \(arguments.query) (providers tried: \(resolvedProviders().joined(separator: ", ")))"
    }

    private func resolvedProviders() -> [String] {
        var out: [String] = []
        if let k = searchApiKeys["brave_search_api_key"], !k.isEmpty { out.append("Brave Search") }
        if let k = searchApiKeys["exa_api_key"], !k.isEmpty { out.append("Exa") }
        if let k = searchApiKeys["tavily_api_key"], !k.isEmpty { out.append("Tavily") }
        out.append("DuckDuckGo")
        return out
    }

    // Brave Search: top-3 result title + description snippets
    private func searchBrave(query: String, apiKey: String) async throws -> String {
        guard let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "https://api.search.brave.com/res/v1/web/search?q=\(encoded)&count=5")
        else { return "" }
        var req = URLRequest(url: url)
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue(apiKey, forHTTPHeaderField: "X-Subscription-Token")
        let (data, _) = try await URLSession.shared.data(for: req)
        struct Result: Decodable { let title: String; let description: String? }
        struct Web: Decodable { let results: [Result]? }
        struct Resp: Decodable { let web: Web? }
        guard let resp = try? JSONDecoder().decode(Resp.self, from: data),
              let results = resp.web?.results else { return "" }
        return results.prefix(3)
            .map { "\($0.title): \($0.description ?? "")" }
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
    }

    // Exa (AI-native): top-3 result highlights
    private func searchExa(query: String, apiKey: String) async throws -> String {
        guard let url = URL(string: "https://api.exa.ai/search") else { return "" }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        let body: [String: Any] = [
            "query": query,
            "numResults": 3,
            "contents": ["highlights": ["numSentences": 2]]
        ]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await URLSession.shared.data(for: req)
        struct Result: Decodable { let title: String?; let highlights: [String]? }
        struct Resp: Decodable { let results: [Result]? }
        guard let resp = try? JSONDecoder().decode(Resp.self, from: data),
              let results = resp.results else { return "" }
        return results.prefix(3)
            .flatMap { ([($0.title ?? "")] + ($0.highlights ?? [])) }
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
    }

    // Tavily (AI-native RAG search): answer + top-3 result content snippets
    private func searchTavily(query: String, apiKey: String) async throws -> String {
        guard let url = URL(string: "https://api.tavily.com/search") else { return "" }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = [
            "api_key": apiKey,
            "query": query,
            "search_depth": "basic",
            "max_results": 5
        ]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await URLSession.shared.data(for: req)
        struct Result: Decodable { let title: String?; let content: String? }
        struct Resp: Decodable { let results: [Result]?; let answer: String? }
        guard let resp = try? JSONDecoder().decode(Resp.self, from: data) else { return "" }
        let snippets = ([resp.answer]
            + (resp.results ?? []).prefix(3).map { r in
                r.title.map { "\($0): \(r.content ?? "")" } ?? r.content
            })
            .compactMap { $0 }
            .filter { !$0.isEmpty }
        return snippets.joined(separator: "\n")
    }

    // DuckDuckGo Instant Answer: Wikipedia abstracts + related topics (free, no key).
    // Returns results for concept/topic queries (e.g. "calisthenics"); returns empty
    // for specific multi-word exercise phrases that don't match a Wikipedia article.
    // no_redirect=1 prevents redirect-only responses for single-entity queries.
    private func searchDuckDuckGo(query: String) async throws -> String {
        guard let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "https://api.duckduckgo.com/?q=\(encoded)&format=json&no_html=1&skip_disambig=1&no_redirect=1")
        else { return "" }
        let (data, _) = try await URLSession.shared.data(from: url)
        struct Topic: Decodable {
            let text: String?
            enum CodingKeys: String, CodingKey { case text = "Text" }
        }
        struct Resp: Decodable {
            let abstractText: String; let relatedTopics: [Topic]; let answer: String
            enum CodingKeys: String, CodingKey {
                case abstractText = "AbstractText"; case relatedTopics = "RelatedTopics"; case answer = "Answer"
            }
        }
        guard let ddg = try? JSONDecoder().decode(Resp.self, from: data) else { return "" }
        return ([ddg.answer, ddg.abstractText] + ddg.relatedTopics.compactMap(\.text))
            .filter { !$0.isEmpty }
            .prefix(5)
            .joined(separator: "\n")
    }
}

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

        if request.enableSearch {
            // Two-phase generation: Phase 1 researches exercises via web search,
            // Phase 2 generates the schema-constrained JSON plan on the same session
            // (transcript from Phase 1 persists as context for Phase 2).
            let searchTool = WebSearchTool(searchApiKeys: request.searchApiKeys ?? [:])
            let researchSession = LanguageModelSession(
                tools: [searchTool],
                instructions: request.system
            )
            let researchPrompt = """
            \(request.user)

            ---

            Based on the user profile and constraints above, use the search tool to look up \
            specific exercises and example workouts that match the available equipment and \
            session duration. Perform 2-3 targeted searches before the plan is generated.
            """
            _ = try await researchSession.respond(to: researchPrompt, options: opts)

            let result = try await researchSession.respond(
                to: request.user,
                schema: genSchema,
                includeSchemaInPrompt: false,
                options: opts
            )
            text = result.content.jsonString
        } else {
            let result = try await session.respond(
                to: request.user,
                schema: genSchema,
                includeSchemaInPrompt: false,
                options: opts
            )
            text = result.content.jsonString
        }
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
