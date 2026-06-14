import XCTest
@testable import CoachInferCore

// MARK: - Request

final class RequestTests: XCTestCase {
    func testDecodeFullPayload() throws {
        let json = #"{"system":"sys","user":"usr","max_tokens":512}"#.data(using: .utf8)!
        let req = try JSONDecoder().decode(Request.self, from: json)
        XCTAssertEqual(req.system, "sys")
        XCTAssertEqual(req.user, "usr")
        XCTAssertEqual(req.maxTokens, 512)
        XCTAssertNil(req.schema)
    }

    func testDecodeSnakeCaseKey() throws {
        let json = #"{"system":"s","user":"u","max_tokens":100}"#.data(using: .utf8)!
        let req = try JSONDecoder().decode(Request.self, from: json)
        XCTAssertEqual(req.maxTokens, 100)
    }

    func testDecodeEmptyStrings() throws {
        let json = #"{"system":"","user":"","max_tokens":0}"#.data(using: .utf8)!
        let req = try JSONDecoder().decode(Request.self, from: json)
        XCTAssertEqual(req.system, "")
        XCTAssertEqual(req.user, "")
        XCTAssertEqual(req.maxTokens, 0)
    }

    func testDecodeInvalidJSONThrows() {
        let json = "not json".data(using: .utf8)!
        XCTAssertThrowsError(try JSONDecoder().decode(Request.self, from: json))
    }

    func testDecodeMissingFieldThrows() {
        // max_tokens is required
        let json = #"{"system":"s","user":"u"}"#.data(using: .utf8)!
        XCTAssertThrowsError(try JSONDecoder().decode(Request.self, from: json))
    }

    func testMemberwiseInit() {
        let req = Request(system: "a", user: "b", maxTokens: 42)
        XCTAssertEqual(req.system, "a")
        XCTAssertEqual(req.user, "b")
        XCTAssertEqual(req.maxTokens, 42)
        XCTAssertNil(req.schema)
    }

    func testDecodeWithFlatStringSchema() throws {
        let json = #"""
        {
          "system": "sys",
          "user": "usr",
          "max_tokens": 256,
          "schema": {
            "type": "object",
            "name": "Root",
            "properties": [
              {"name": "title", "schema": {"type": "string"}, "is_optional": false},
              {"name": "count", "schema": {"type": "integer"}, "is_optional": true}
            ]
          }
        }
        """#.data(using: .utf8)!
        let req = try JSONDecoder().decode(Request.self, from: json)
        let schema = try XCTUnwrap(req.schema)
        XCTAssertEqual(schema.type, "object")
        XCTAssertEqual(schema.name, "Root")
        XCTAssertEqual(schema.properties?.count, 2)
        XCTAssertEqual(schema.properties?[0].name, "title")
        XCTAssertEqual(schema.properties?[0].schema.type, "string")
        XCTAssertFalse(schema.properties?[0].isOptional ?? true)
        XCTAssertEqual(schema.properties?[1].name, "count")
        XCTAssertTrue(schema.properties?[1].isOptional ?? false)
    }

    func testDecodeWithNestedArraySchema() throws {
        let json = #"""
        {
          "system": "s",
          "user": "u",
          "max_tokens": 128,
          "schema": {
            "type": "array",
            "items": {"type": "string"},
            "min": 1,
            "max": 7
          }
        }
        """#.data(using: .utf8)!
        let req = try JSONDecoder().decode(Request.self, from: json)
        let schema = try XCTUnwrap(req.schema)
        XCTAssertEqual(schema.type, "array")
        XCTAssertEqual(schema.items?.type, "string")
        XCTAssertEqual(schema.min, 1)
        XCTAssertEqual(schema.max, 7)
    }

    func testDecodeEnableSearchTrue() throws {
        let json = #"{"system":"s","user":"u","max_tokens":256,"enable_search":true}"#.data(using: .utf8)!
        let req = try JSONDecoder().decode(Request.self, from: json)
        XCTAssertTrue(req.enableSearch)
    }

    func testDecodeEnableSearchAbsent() throws {
        let json = #"{"system":"s","user":"u","max_tokens":256}"#.data(using: .utf8)!
        let req = try JSONDecoder().decode(Request.self, from: json)
        XCTAssertFalse(req.enableSearch, "enable_search should default to false when absent")
    }

    func testDecodeSearchApiKeys() throws {
        let json = #"""
        {
          "system": "s",
          "user": "u",
          "max_tokens": 256,
          "enable_search": true,
          "search_api_keys": {
            "brave_search_api_key": "test-key-brave",
            "exa_api_key": "test-key-exa",
            "tavily_api_key": "tvly-test-key"
          }
        }
        """#.data(using: .utf8)!
        let req = try JSONDecoder().decode(Request.self, from: json)
        XCTAssertTrue(req.enableSearch)
        let keys = try XCTUnwrap(req.searchApiKeys)
        XCTAssertEqual(keys["brave_search_api_key"], "test-key-brave")
        XCTAssertEqual(keys["exa_api_key"], "test-key-exa")
        XCTAssertEqual(keys["tavily_api_key"], "tvly-test-key")
    }
}

// MARK: - Response

final class ResponseTests: XCTestCase {
    func testEncodeProducesExpectedKeys() throws {
        let resp = Response(text: "hello", model: "apple/on-device")
        let data = try JSONEncoder().encode(resp)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: String]
        XCTAssertEqual(dict["text"], "hello")
        XCTAssertEqual(dict["model"], "apple/on-device")
    }

    func testEncodeEmptyText() throws {
        let resp = Response(text: "", model: "apple/on-device")
        let data = try JSONEncoder().encode(resp)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: String]
        XCTAssertEqual(dict["text"], "")
    }

    func testEncodeTextPreservesContent() throws {
        let body = "Week plan:\n- Monday: Strength\n- Tuesday: Cardio"
        let resp = Response(text: body, model: "apple/on-device")
        let data = try JSONEncoder().encode(resp)
        let decoded = try JSONDecoder().decode(Response.self, from: data)
        XCTAssertEqual(decoded.text, body)
        XCTAssertEqual(decoded.model, "apple/on-device")
    }

    func testMemberwiseInit() {
        let resp = Response(text: "ok", model: "apple/on-device")
        XCTAssertEqual(resp.text, "ok")
        XCTAssertEqual(resp.model, "apple/on-device")
        XCTAssertNil(resp.error)
    }

    func testEncodeOmitsErrorKeyWhenNil() throws {
        let resp = Response(text: "ok", model: "apple/on-device")
        let data = try JSONEncoder().encode(resp)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertNil(dict["error"], "error key should be absent when nil")
    }

    func testEncodeIncludesErrorWhenPresent() throws {
        let resp = Response(text: "", model: "apple/on-device", error: "Model unavailable")
        let data = try JSONEncoder().encode(resp)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(dict["error"] as? String, "Model unavailable")
        XCTAssertEqual(dict["text"] as? String, "")
    }

    func testDecodeRoundTripsError() throws {
        let original = Response(text: "", model: "apple/on-device", error: "Something failed")
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(Response.self, from: data)
        XCTAssertEqual(decoded.error, "Something failed")
    }
}
