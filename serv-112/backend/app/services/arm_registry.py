class ArmRegistry:
    def __init__(self) -> None:
        self._used: set[int] = set()

    def acquire(self) -> int:
        arm_number = 1

        while arm_number in self._used:
            arm_number += 1

        self._used.add(arm_number)

        return arm_number

    def release(self, arm_number: int) -> None:
        self._used.discard(arm_number)

    def count(self) -> int:
        return len(self._used)


arm_registry = ArmRegistry()