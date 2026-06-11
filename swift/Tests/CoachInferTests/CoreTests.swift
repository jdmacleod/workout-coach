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
    }
}
