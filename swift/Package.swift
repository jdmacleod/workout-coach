// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CoachInfer",
    platforms: [.macOS(.v26)],
    targets: [
        .executableTarget(
            name: "CoachInfer",
            path: "Sources/CoachInfer"
        )
    ]
)
