pub struct Item {
    sku: String,
}

impl Item {
    pub fn new(sku: String) -> Self {
        Item { sku }
    }

    pub fn label(&self) -> String {
        self.sku.clone()
    }
}
