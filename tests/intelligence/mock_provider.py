from coach.intelligence.provider import InferenceProvider, InferenceRequest, InferenceResponse


class MockInferenceProvider(InferenceProvider):
    """Configurable mock provider for testing.

    Set response_text to control what infer() returns.
    Set available to control is_available().
    """

    def __init__(self, response_text: str = '{"result": "mock"}', available: bool = True) -> None:
        self.response_text = response_text
        self.available = available
        self.calls: list[InferenceRequest] = []

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        self.calls.append(request)
        return InferenceResponse(
            text=self.response_text,
            provider="mock",
            model="mock-model",
        )

    def is_available(self) -> bool:
        return self.available

    def provider_name(self) -> str:
        return "mock"
