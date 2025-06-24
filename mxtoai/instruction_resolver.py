from mxtoai import exceptions
from mxtoai._logging import get_logger
from mxtoai.schemas import ProcessingInstructions

logger = get_logger(__name__)


class ProcessingInstructionsResolver:
    """
    Resolves processing instructions based on email handle names or aliases.

    This class is responsible for:
    - Registering predefined and custom email handle instructions.
    - Resolving a given handle (or its alias) to its corresponding instructions.
    - Preventing alias/handle conflicts unless explicitly allowed.
    - Supporting runtime extensibility via dynamic handle registration.

    Attributes:
        handle_map (Dict[str, EmailHandleInstructions]): Maps handles and aliases to their instruction objects.

    """

    def __init__(self, default_instructions: list[ProcessingInstructions]):
        """
        Initialize the resolver with a list of default handle instructions.

        Args:
            default_instructions (List[EmailHandleInstructions]): List of predefined handle configurations.

        """
        self.handle_map: dict[str, ProcessingInstructions] = {}
        self.register_handles(default_instructions)

    def register_handles(self, instructions_list: list[ProcessingInstructions], *, overwrite: bool = False):
        """
        Registers a list of handle instructions (including aliases).

        Args:
            instructions_list (List[EmailHandleInstructions]): Handles and aliases to register.
            overwrite (bool): If True, allows existing handles/aliases to be overwritten.

        Raises:
            ValueError: If a handle or alias is already registered and overwrite is False.

        """
        for instructions in instructions_list:
            all_names = [instructions.handle, *instructions.aliases]
            for name in all_names:
                if name in self.handle_map and not overwrite:
                    msg = f"Handle or alias '{name}' already registered. Use `overwrite=True` to replace."
                    raise exceptions.HandleAlreadyExistsException(msg)
                self.handle_map[name] = instructions

    def add_custom_handle(self, custom_instruction: ProcessingInstructions, *, overwrite: bool = False):
        """
        Adds a single custom handle instruction.

        Args:
            custom_instruction (EmailHandleInstructions): The custom handle config to add.
            overwrite (bool): If True, allows overwriting existing handles/aliases.

        """
        self.register_handles([custom_instruction], overwrite=overwrite)

    def __call__(self, handle: str) -> ProcessingInstructions:
        """
        Resolves a handle or alias to its corresponding EmailHandleInstructions.

        Args:
            handle (str): The handle or alias name.

        Returns:
            EmailHandleInstructions: The matched instruction object.

        Raises:
            ValueError: If the handle is not registered.

        """
        if handle not in self.handle_map:
            logger.debug("This email handle is not supported!")
            msg = "This email handle is not supported. Please visit https://mxtoai.com/docs/email-handles to learn about supported email handles."
            raise exceptions.UnspportedHandleException(msg)
        return self.handle_map[handle]

    def list_available_handles(self) -> list[str]:
        """
        Lists all unique handle names currently registered (excluding aliases).

        Returns:
            List[str]: A list of unique registered handle names.

        """
        return list({instr.handle for instr in self.handle_map.values()})
