class UnspportedHandleException(Exception):
    def __init__(self, message: str):
        super().__init__(message)

class HandleAlreadyExistsException(Exception):
    def __init__(self, message: str):
        super().__init__(message)

class EnvironmentVariableNotFoundException(Exception):
    def __init__(self, message: str):
        super().__init__(message)

class ModelListNotFoundException(Exception):
    def __init__(self, message: str):
        super().__init__(message)

class ModelConfigFileNotFoundException(Exception):
    def __init__(self, message: str):
        super().__init__(message)
