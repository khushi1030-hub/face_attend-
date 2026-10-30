document.addEventListener('DOMContentLoaded', () => {
  const menu = document.querySelector('#menu-toggle');
  const sidebar = document.querySelector('#sidebar');
  if (menu && sidebar) {
    menu.addEventListener('click', () => {
      const open = sidebar.classList.toggle('open');
      menu.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('click', (event) => {
      if (window.innerWidth <= 820 && sidebar.classList.contains('open') && !sidebar.contains(event.target) && event.target !== menu) {
        sidebar.classList.remove('open');
        menu.setAttribute('aria-expanded', 'false');
      }
    });
  }
  document.querySelectorAll('.toast-close').forEach((button) => {
    button.addEventListener('click', () => button.closest('.toast')?.remove());
  });
  document.querySelectorAll('.toast').forEach((toast) => {
    window.setTimeout(() => toast.remove(), 6500);
  });
  document.querySelectorAll('[data-width]').forEach((element) => {
    const value = Number(element.dataset.width);
    if (Number.isFinite(value)) element.style.width = `${Math.max(0, Math.min(100, value))}%`;
  });
});

window.getCookie = function getCookie(name) {
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split('=')[1]) : '';
};
