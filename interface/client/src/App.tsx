import { Route, Switch } from "wouter";
import Home from "./pages/Home";

export default function App() {
  return <Switch><Route path="/" component={Home} /><Route path="/:rest*" component={Home} /></Switch>;
}
