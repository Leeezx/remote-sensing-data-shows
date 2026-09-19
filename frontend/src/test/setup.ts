import '@testing-library/jest-dom'

// jsdom 29 提供 HTMLDialogElement 但不实现 showModal/close，
// 这里补上被测组件依赖的最小行为。仅测试夹具，不影响生产代码。
HTMLDialogElement.prototype.showModal ??= function showModal(this: HTMLDialogElement) {
  this.setAttribute('open', '')
}
HTMLDialogElement.prototype.close ??= function close(this: HTMLDialogElement) {
  this.removeAttribute('open')
  this.dispatchEvent(new Event('close'))
}
