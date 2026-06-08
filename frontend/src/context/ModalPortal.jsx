import ReactDOM from 'react-dom'

export function ModalPortal({ children }) {
  return ReactDOM.createPortal(
    children,
    document.body
  )
}
