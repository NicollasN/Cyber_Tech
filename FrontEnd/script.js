const productGrid = document.getElementById('productGrid');
const filterButtons = document.querySelectorAll('.filter-btn');
const priceFormatter = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL'
});
let products = [];
let selectedCategory = 'all';

function renderProducts() {
  const filteredProducts = products.filter(
    (product) =>
      selectedCategory === 'all' || product.category === selectedCategory
  );

  productGrid.replaceChildren();

  filteredProducts.forEach((product) => {
    const card = document.createElement('article');
    card.className = 'product-card';

    const image = document.createElement('img');
    image.src = product.image;
    image.alt = product.name;
    image.loading = 'lazy';

    const info = document.createElement('div');
    info.className = 'product-info';

    const tag = document.createElement('span');
    tag.className = 'product-tag';
    tag.textContent = product.tag;

    const name = document.createElement('h3');
    name.textContent = product.name;

    const description = document.createElement('p');
    description.className = 'product-description';
    description.textContent = product.description;

    const meta = document.createElement('div');
    meta.className = 'product-meta';

    const price = document.createElement('span');
    price.className = 'price';
    price.textContent = priceFormatter.format(product.price);

    const link = document.createElement('a');
    link.className = 'buy-link';
    link.href = product.affiliateUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer sponsored';
    link.textContent = 'Ver oferta';

    meta.append(price);
    info.append(tag, name, description, meta, link);
    card.append(image, info);
    productGrid.append(card);
  });

  if (filteredProducts.length === 0) {
    const emptyState = document.createElement('p');
    emptyState.className = 'products-message';
    emptyState.textContent =
      products.length === 0
        ? 'Nenhum produto cadastrado no momento.'
        : 'Nenhum produto nesta categoria.';
    productGrid.append(emptyState);
  }
}

filterButtons.forEach((button) => {
  button.addEventListener('click', () => {
    filterButtons.forEach((btn) => btn.classList.remove('active'));
    button.classList.add('active');
    selectedCategory = button.dataset.category;
    renderProducts();
  });
});

async function loadProducts() {
  try {
    const response = await fetch('/api/products');
    if (!response.ok) {
      throw new Error('Não foi possível carregar os produtos.');
    }

    const data = await response.json();
    products = data.products;
    renderProducts();
  } catch (error) {
    productGrid.replaceChildren();
    const message = document.createElement('p');
    message.className = 'products-message';
    message.textContent =
      'Não foi possível carregar os produtos. Tente novamente mais tarde.';
    productGrid.append(message);
    console.error('Falha ao carregar o catálogo:', error);
  }
}

loadProducts();
