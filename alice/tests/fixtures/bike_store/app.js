let cart = [];
function addToCart(name, price) {
  cart.push({name, price});
  document.getElementById('cart-count').textContent = cart.length;
}
