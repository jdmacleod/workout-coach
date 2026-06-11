# CoachInfer — Swift CLI bridge for Apple's FoundationModels framework
# Self-documenting: run 'make' or 'make help' to list available targets.
# From the repo root: make -C swift [target]
.DEFAULT_GOAL := help

BINARY      := CoachInfer
RELEASE_DIR := .build/release
DEBUG_DIR   := .build/debug

.PHONY: help build debug test clean smoke

help: ## Show available targets
	@echo
	@echo "Usage: make [target]"
	@echo
	@awk -F ':.*## ' '/^[A-Za-z0-9_.-]+:.*## /{printf "  %-8s %s\n", $$1, $$2}' Makefile | sort
	@echo

build: ## Compile the release binary → .build/release/CoachInfer
	swift build -c release

debug: ## Compile a debug binary with symbols → .build/debug/CoachInfer
	swift build

test: ## Run the Swift test suite
	swift test

clean: ## Remove all build artefacts (.build/)
	swift package clean

smoke: build ## Build then run end-to-end smoke test (requires Apple Intelligence)
	@HW_MODEL=$$(sysctl -n hw.model 2>/dev/null || echo "unknown"); \
	HW_CHIP=$$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "unknown"); \
	OS_VER=$$(sw_vers -productVersion 2>/dev/null || echo "unknown"); \
	OS_BUILD=$$(sw_vers -buildVersion 2>/dev/null || echo "unknown"); \
	FM_PLIST="/System/Library/Frameworks/FoundationModels.framework/Resources/Info.plist"; \
	FM_BUILD=$$(plutil -extract CFBundleVersion raw "$$FM_PLIST" 2>/dev/null | tr -d '\n'); \
	FM_BUILD=$${FM_BUILD:-n/a}; \
	echo ""; \
	echo "  CoachInfer smoke test"; \
	echo "  ─────────────────────────────────────────────"; \
	printf "  %-22s %s  %s\n" "Hardware:" "$$HW_MODEL" "$$HW_CHIP"; \
	printf "  %-22s %s (%s)\n" "macOS:" "$$OS_VER" "$$OS_BUILD"; \
	printf "  %-22s FoundationModels %s\n" "Apple Intelligence:" "$$FM_BUILD"; \
	echo ""; \
	T0=$$(python3 -c "import time; print(int(time.time()*1000))"); \
	RESPONSE=$$(printf '{"system":"You are a test assistant. Follow instructions exactly.","user":"Respond with exactly the phrase: CoachInfer OK","max_tokens":20}' \
		| ./$(RELEASE_DIR)/$(BINARY)); \
	STATUS=$$?; \
	T1=$$(python3 -c "import time; print(int(time.time()*1000))"); \
	ELAPSED_MS=$$((T1 - T0)); \
	ELAPSED=$$(python3 -c "ms=$$ELAPSED_MS; print(f'{ms}ms') if ms < 1000 else print(f'{ms/1000:.1f}s')"); \
	TEXT=$$(python3 -c "import json,sys; print(json.loads('$$RESPONSE').get('text',''))" 2>/dev/null || echo "$$RESPONSE"); \
	echo "  $$TEXT"; \
	echo ""; \
	printf "  %-22s %s\n" "Time:" "$$ELAPSED"; \
	if [ $$STATUS -eq 0 ] && [ -n "$$RESPONSE" ]; then \
		printf "  %-22s PASS\n" "Status:"; \
	else \
		printf "  %-22s FAIL (exit %s)\n" "Status:" "$$STATUS"; \
		exit 1; \
	fi; \
	echo ""
