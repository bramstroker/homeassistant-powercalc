from typing import Any, Protocol

import inquirer


class Answerable(Protocol):
    def get_questions(self) -> list[inquirer.questions.Question]:
        """Get questions to ask for the controller"""
        ...

    def process_answers(self, answers: dict[str, Any]) -> None:
        """Process the answers of the questions"""
        ...
