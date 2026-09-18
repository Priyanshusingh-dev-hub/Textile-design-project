/* ===================================================================
   Sufiyan Consultancy Services — Scripts
=================================================================== */
(function () {
  'use strict';

  // ---- Config: update this number to the business WhatsApp number ----
  var WHATSAPP_NUMBER = '919999999999'; // country code + number, no '+'

  var navbar   = document.getElementById('navbar');
  var navToggle = document.getElementById('navToggle');
  var navLinks = document.getElementById('navLinks');
  var toastEl  = document.getElementById('toast');

  /* ---------- Mobile menu ---------- */
  if (navToggle && navLinks) {
    navToggle.addEventListener('click', function () {
      navToggle.classList.toggle('active');
      navLinks.classList.toggle('open');
    });
    navLinks.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        navToggle.classList.remove('active');
        navLinks.classList.remove('open');
      });
    });
  }

  /* ---------- Navbar shadow on scroll ---------- */
  function onScroll() {
    if (window.scrollY > 10) navbar.classList.add('scrolled');
    else navbar.classList.remove('scrolled');
  }
  window.addEventListener('scroll', onScroll);
  onScroll();

  /* ---------- Reveal on scroll ---------- */
  var revealTargets = document.querySelectorAll(
    '.service-card, .team-card, .step, .testi-card, .about-content, .about-media, .section-head'
  );
  revealTargets.forEach(function (el) { el.classList.add('reveal'); });

  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    revealTargets.forEach(function (el) { io.observe(el); });
  } else {
    revealTargets.forEach(function (el) { el.classList.add('visible'); });
  }

  /* ---------- Toast ---------- */
  var toastTimer;
  function showToast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, 4000);
  }

  /* ---------- Forms → WhatsApp ---------- */
  function handleForm(form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var data = new FormData(form);
      var name    = (data.get('name')    || '').trim();
      var phone   = (data.get('phone')   || '').trim();
      var email   = (data.get('email')   || '').trim();
      var service = (data.get('service') || '').trim();
      var message = (data.get('message') || '').trim();

      var lines = ['*New Enquiry — Sufiyan Consultancy*', ''];
      if (name)    lines.push('Name: ' + name);
      if (phone)   lines.push('Phone: ' + phone);
      if (email)   lines.push('Email: ' + email);
      if (service) lines.push('Service: ' + service);
      if (message) lines.push('Message: ' + message);

      var url = 'https://wa.me/' + WHATSAPP_NUMBER + '?text=' +
        encodeURIComponent(lines.join('\n'));

      showToast('Thanks ' + (name || '') + '! Opening WhatsApp to send your enquiry…');
      window.open(url, '_blank');
      form.reset();
    });
  }
  document.querySelectorAll('form[data-form]').forEach(handleForm);

  /* ---------- Footer year ---------- */
  var yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

})();
