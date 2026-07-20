from animals import Animal


class Dog(Animal):
    """A dog overrides speak and inherits eat."""

    def speak(self):
        return "woof"

    def fetch(self):
        snack = self.eat()
        return f"fetched the ball, then {snack}"


def train_dog():
    dog = Dog()
    return dog.speak()
