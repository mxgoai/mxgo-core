class UnspportedHandleError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class HandleAlreadyExistsError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class EnvironmentVariableNotFoundError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class ModelListNotFoundError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class ModelConfigFileNotFoundError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
