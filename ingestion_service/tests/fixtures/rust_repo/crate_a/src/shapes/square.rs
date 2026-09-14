use super::Circle;

pub struct Square {
    side: f64,
}

impl Square {
    pub fn new(side: f64) -> Self {
        Square { side }
    }

    pub fn area(&self) -> f64 {
        self.side * self.side
    }

    pub fn make_circle(radius: f64) -> Circle {
        Circle::new(radius)
    }
}
