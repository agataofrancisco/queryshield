import { Component } from "react";

// Um dado inesperado não pode derrubar o ecrã: a secção falha, o resto continua.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="notice notice-error" role="alert">
          Não foi possível mostrar esta secção. A consulta continua disponível.
        </div>
      );
    }
    return this.props.children;
  }
}
