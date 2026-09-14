pub mod kennel;
pub mod shapes;

pub struct Animal {
    name: String,
}

impl Animal {
    pub fn new(name: String) -> Self {
        Animal { name }
    }

    pub fn speak(&self) -> String {
        format!("{} speaks", self.name)
    }
}

impl Animal {
    pub fn describe(&self) -> String {
        self.speak()
    }
}

pub trait Movable {
    fn move_to(&self, x: i32, y: i32);
}

impl Movable for Animal {
    fn move_to(&self, _x: i32, _y: i32) {
        self.speak();
    }
}

pub struct Item {
    label: String,
}
