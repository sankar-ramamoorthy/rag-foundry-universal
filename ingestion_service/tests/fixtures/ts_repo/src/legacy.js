const { helper } = require("./util");

const arrowExport = () => {
  setTimeout(() => {
    console.log("anon callback, not a symbol");
  }, 1);
  return helper();
};

module.exports = { arrowExport };
