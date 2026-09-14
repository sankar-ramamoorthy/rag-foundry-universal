use crate::Animal;

pub struct Dog {
    name: String,
}

impl Dog {
    pub fn new() -> Self {
        Dog { name: "Rex".to_string() }
    }

    pub fn greet(&self) -> String {
        self.bark()
    }

    fn bark(&self) -> String {
        format!("{} barks", self.name)
    }

    pub fn make_default() -> Self {
        Self::new()
    }

    pub fn make_animal() -> Animal {
        Animal::new("Buddy".to_string())
    }
}
