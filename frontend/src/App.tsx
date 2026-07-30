import "./App.css";
import { useEffect, useState } from "react";
import { getHealth } from "./api";

type ConnectionState = "checking" | "connected" | "unavailable";

function App() {
   const [connectionState, setConnectionState] =
      useState<ConnectionState>("checking");

   useEffect(() => {
      getHealth()
         .then(() => setConnectionState("connected"))
         .catch(() => setConnectionState("unavailable"));
   }, []);

   return (
      <main className="app">
         <section>
            <p className="app__name">Ludex</p>
            <h1>Find your next game.</h1>
            <p>
               Ludex helps you choose what to play from your existing Steam
               library.
            </p>
            <p className={`app__status app__status--${connectionState}`}>
               Backend: {connectionState}
            </p>
         </section>
      </main>
   );
}

export default App;
