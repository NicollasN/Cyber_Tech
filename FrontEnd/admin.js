const loginView = document.getElementById('loginView');
const dashboard = document.getElementById('dashboard');
const loginForm = document.getElementById('loginForm');
const loginMessage = document.getElementById('loginMessage');
const productForm = document.getElementById('productForm');
const productMessage = document.getElementById('productMessage');
const dashboardMessage = document.getElementById('dashboardMessage');
const productsList = document.getElementById('productsList');
const productCount = document.getElementById('productCount');
const productSearch = document.getElementById('productSearch');
const editorTitle = document.getElementById('editorTitle');
const editorEyebrow = document.getElementById('editorEyebrow');
const saveProductButton = document.getElementById('saveProductButton');
const cancelEditButton = document.getElementById('cancelEditButton');
const currency = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL'
});
let products = [];
let editingProductId = null;

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers
    }
  });
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || 'Não foi possível concluir a operação.');
  }

  return data;
}

function showLogin() {
  dashboard.hidden = true;
  loginView.hidden = false;
  document.title = 'Catálogo | Cyber Tech';
}

function showDashboard() {
  loginView.hidden = true;
  dashboard.hidden = false;
  document.title = 'Catálogo | Cyber Tech';
  loadProducts();
}

function showDashboardMessage(message, isError = false) {
  dashboardMessage.textContent = message;
  dashboardMessage.dataset.error = String(isError);
}

function createActionButton(label, action, isDanger = false) {
  const button = document.createElement('button');
  button.className = `row-action${isDanger ? ' row-action-danger' : ''}`;
  button.type = 'button';
  button.textContent = label;
  button.addEventListener('click', action);
  return button;
}

function renderProducts() {
  const query = productSearch.value.trim().toLocaleLowerCase('pt-BR');
  const visibleProducts = products.filter((product) =>
    product.name.toLocaleLowerCase('pt-BR').includes(query)
  );

  productCount.textContent = String(products.length);
  productsList.replaceChildren();

  if (visibleProducts.length === 0) {
    const emptyMessage = document.createElement('p');
    emptyMessage.className = 'empty-catalog';
    emptyMessage.textContent = query
      ? 'Nenhum produto corresponde à busca.'
      : 'Seu catálogo ainda está vazio. Adicione um produto para ele aparecer na loja.';
    productsList.append(emptyMessage);
    return;
  }

  visibleProducts.forEach((product) => {
    const row = document.createElement('article');
    row.className = 'product-row';

    const image = document.createElement('img');
    image.className = 'product-thumb';
    image.src = product.image;
    image.alt = '';
    image.loading = 'lazy';

    const info = document.createElement('div');
    info.className = 'product-row-info';

    const name = document.createElement('h3');
    name.className = 'product-row-name';
    name.textContent = product.name;

    const meta = document.createElement('p');
    meta.className = 'product-row-meta';
    meta.textContent = `${product.tag} · ${product.category}`;

    const price = document.createElement('p');
    price.className = 'product-row-price';
    price.textContent = currency.format(product.price);

    const actions = document.createElement('div');
    actions.className = 'product-row-actions';
    actions.append(
      createActionButton('Editar', () => startEditing(product)),
      createActionButton('Excluir', () => deleteProduct(product), true)
    );

    info.append(name, meta, price);
    row.append(image, info, actions);
    productsList.append(row);
  });
}

function clearEditor() {
  editingProductId = null;
  productForm.reset();
  editorEyebrow.textContent = 'NOVO ITEM';
  editorTitle.textContent = 'Adicionar produto';
  saveProductButton.innerHTML = 'Salvar produto <span aria-hidden="true">→</span>';
  cancelEditButton.hidden = true;
  productMessage.textContent = '';
}

function startEditing(product) {
  editingProductId = product.id;
  productForm.elements.name.value = product.name;
  productForm.elements.category.value = product.category;
  productForm.elements.tag.value = product.tag;
  productForm.elements.price.value = product.price;
  productForm.elements.image.value = product.image;
  productForm.elements.affiliateUrl.value = product.affiliateUrl;
  productForm.elements.description.value = product.description;
  editorEyebrow.textContent = 'EDITANDO ITEM';
  editorTitle.textContent = 'Editar produto';
  saveProductButton.innerHTML = 'Salvar alterações <span aria-hidden="true">→</span>';
  cancelEditButton.hidden = false;
  productMessage.textContent = '';
  document.getElementById('productName').focus();
}

async function loadProducts() {
  try {
    const data = await request('/api/products');
    products = data.products;
    renderProducts();
  } catch (error) {
    productsList.replaceChildren();
    const errorMessage = document.createElement('p');
    errorMessage.className = 'empty-catalog';
    errorMessage.textContent = error.message;
    productsList.append(errorMessage);
    showDashboardMessage(error.message, true);
  }
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  loginMessage.textContent = '';
  const formData = new FormData(loginForm);

  try {
    await request('/api/login', {
      method: 'POST',
      body: JSON.stringify({
        email: formData.get('email'),
        password: formData.get('password')
      })
    });
    loginForm.reset();
    showDashboard();
  } catch (error) {
    loginMessage.textContent = error.message;
  }
});

productForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  productMessage.textContent = '';
  saveProductButton.disabled = true;

  const formData = new FormData(productForm);
  const payload = {
    name: formData.get('name'),
    category: formData.get('category'),
    tag: formData.get('tag'),
    price: formData.get('price'),
    image: formData.get('image'),
    affiliateUrl: formData.get('affiliateUrl'),
    description: formData.get('description')
  };
  const isEditing = editingProductId !== null;
  const path = isEditing
    ? `/api/products/${editingProductId}`
    : '/api/products';

  try {
    const data = await request(path, {
      method: isEditing ? 'PUT' : 'POST',
      body: JSON.stringify(payload)
    });
    const savedProduct = data.product;

    if (editingProductId) {
      products = products.map((product) =>
        product.id === savedProduct.id ? savedProduct : product
      );
    } else {
      products.unshift(savedProduct);
    }

    clearEditor();
    renderProducts();
    showDashboardMessage(
      isEditing ? 'Alterações salvas na loja.' : 'Produto adicionado à loja.'
    );
  } catch (error) {
    productMessage.textContent = error.message;
  } finally {
    saveProductButton.disabled = false;
  }
});

async function deleteProduct(product) {
  if (!window.confirm(`Excluir “${product.name}” da loja?`)) {
    return;
  }

  showDashboardMessage('');
  try {
    await request(`/api/products/${product.id}`, { method: 'DELETE' });
    products = products.filter((item) => item.id !== product.id);
    if (editingProductId === product.id) {
      clearEditor();
    }
    renderProducts();
    showDashboardMessage('Produto removido da loja.');
  } catch (error) {
    showDashboardMessage(error.message, true);
  }
}

document.getElementById('newProductButton').addEventListener('click', () => {
  clearEditor();
  document.getElementById('productName').focus();
});

cancelEditButton.addEventListener('click', clearEditor);
productSearch.addEventListener('input', renderProducts);

document.getElementById('logoutButton').addEventListener('click', async () => {
  try {
    await request('/api/logout', { method: 'POST' });
    showLogin();
    showDashboardMessage('');
  } catch (error) {
    showDashboardMessage(error.message, true);
  }
});

async function initialize() {
  try {
    const session = await request('/api/session');
    if (session.authenticated) {
      showDashboard();
      return;
    }
  } catch (error) {
    loginMessage.textContent = error.message;
  }
  showLogin();
}

initialize();
