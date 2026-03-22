document.addEventListener('DOMContentLoaded', function () {
  const authCard      = document.getElementById('auth-card');
  const showSignupBtn = document.getElementById('show-signup-btn');
  const showSigninBtn = document.getElementById('show-signin-btn');
  const panelSignin   = document.getElementById('panel-signin');
  const panelSignup   = document.getElementById('panel-signup');

  function switchPanel(hideEl, showEl, addActive) {
    hideEl.style.transform  = addActive ? 'translateX(-60px)' : 'translateX(60px)';
    hideEl.style.opacity    = '0';

    setTimeout(function () {
      hideEl.style.display  = 'none';
      hideEl.style.opacity  = '';
      hideEl.style.transform = '';

      showEl.style.display    = 'flex';
      showEl.style.transform  = addActive ? 'translateX(60px)' : 'translateX(-60px)';
      showEl.style.opacity    = '0';
      showEl.style.transition = 'none';

      void showEl.offsetWidth;

      showEl.style.transition = 'transform 0.45s ease, opacity 0.45s ease';
      showEl.style.transform  = 'translateX(0)';
      showEl.style.opacity    = '1';
    }, 350);

    if (addActive) {
      authCard.classList.add('active');
    } else {
      authCard.classList.remove('active');
    }
  }

  showSignupBtn.addEventListener('click', function () {
    switchPanel(panelSignin, panelSignup, true);
  });

  showSigninBtn.addEventListener('click', function () {
    switchPanel(panelSignup, panelSignin, false);
  });
});
