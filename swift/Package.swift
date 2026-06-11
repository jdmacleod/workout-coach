// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CoachInfer",
    platforms: [.macOS(.v26)],
    targets: [
        // Pure-logic types shared between the executable and test suite.
        // No FoundationModels dependency — compiles without Apple Intelligence.
        .target(
            name: "CoachInferCore",
            path: "Sources/CoachInferCore"
        ),
        // Thin entry point: reads stdin, calls FoundationModels, writes JSON to stdout.
        .executableTarget(
            name: "CoachInfer",
            dependencies: ["CoachInferCore"],
            path: "Sources/CoachInfer"
        ),
        .testTarget(
            name: "CoachInferTests",
            dependencies: ["CoachInferCore"],
            path: "Tests/CoachInferTests"
        ),
    ]
)
