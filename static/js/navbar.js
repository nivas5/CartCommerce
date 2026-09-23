/**
 * CartCommerce - Responsive Navigation Bar & Hamburger Toggle
 */
document.addEventListener('DOMContentLoaded', function () {
    initNavbar();
});

// Also run immediately if DOM is already ready
if (document.readyState === 'interactive' || document.readyState === 'complete') {
    initNavbar();
}

function initNavbar() {
    const navbars = document.querySelectorAll('.navbar');

    navbars.forEach((navbar) => {
        // Prevent duplicate initialization
        if (navbar.dataset.navbarInitialized === 'true') return;
        navbar.dataset.navbarInitialized = 'true';

        const toggleBtn = navbar.querySelector('.nav-toggle-btn') || navbar.querySelector('#navToggle');
        const navLinks = navbar.querySelector('.nav-links') || navbar.querySelector('#navLinks');

        if (!toggleBtn || !navLinks) return;

        const icon = toggleBtn.querySelector('i');

        function toggleMenu(open) {
            const shouldOpen = open !== undefined ? open : !navLinks.classList.contains('show');
            
            if (shouldOpen) {
                navLinks.classList.add('show');
                toggleBtn.classList.add('active');
                toggleBtn.setAttribute('aria-expanded', 'true');
                if (icon) {
                    icon.classList.remove('fa-bars');
                    icon.classList.add('fa-xmark');
                }
            } else {
                navLinks.classList.remove('show');
                toggleBtn.classList.remove('active');
                toggleBtn.setAttribute('aria-expanded', 'false');
                if (icon) {
                    icon.classList.remove('fa-xmark');
                    icon.classList.add('fa-bars');
                }
            }
        }

        // Toggle button click
        toggleBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            toggleMenu();
        });

        // Close menu when clicking any nav link
        navLinks.querySelectorAll('.nav-link').forEach((link) => {
            link.addEventListener('click', function () {
                if (window.innerWidth <= 920) {
                    toggleMenu(false);
                }
            });
        });

        // Close when clicking outside navbar
        document.addEventListener('click', function (e) {
            if (!navbar.contains(e.target)) {
                if (navLinks.classList.contains('show')) {
                    toggleMenu(false);
                }
            }
        });

        // Close on ESC key
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && navLinks.classList.contains('show')) {
                toggleMenu(false);
            }
        });

        // Reset if window resized to desktop
        window.addEventListener('resize', function () {
            if (window.innerWidth > 920 && navLinks.classList.contains('show')) {
                toggleMenu(false);
            }
        });
    });
}
