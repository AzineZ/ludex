import ludexLogo from "../assets/ludex_logo.png";

/** Displays Ludex's branding and product introduction. */
function Hero() {
   return (
      <header className="app__hero">
         <h1 className="app__logo-heading">
            <img
               className="app__logo"
               src={ludexLogo}
               alt="Ludex — Your next game awaits"
            />
         </h1>
         <p className="app__intro">
            Ludex helps you choose what to play from your existing Steam
            library.
         </p>
      </header>
   );
}

export default Hero;
