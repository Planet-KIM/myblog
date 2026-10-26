/**
 * @file Confirmation dialog before submitting a form (replaces inline
 * onsubmit="return confirm('…')").
 *
 * Put data-confirm="<question>" on a <form>; it only submits when the user
 * accepts the dialog. The listener is delegated on document, so forms that
 * are rendered later are covered too. Loaded on every page by base.html.
 */
(function initConfirmSubmit() {
  /**
   * Cancel the submit of a [data-confirm] form unless the user confirms.
   *
   * @param {SubmitEvent} event - Submit event bubbling to document.
   * @returns {void}
   */
  function confirmBeforeSubmit(event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.confirm) return;
    if (!window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  }

  document.addEventListener('submit', confirmBeforeSubmit);
})();
