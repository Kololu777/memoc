{
  description = "memoc - repository memory books CLI";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { self, nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python312;
        in
        {
          default = python.pkgs.buildPythonApplication {
            pname = "memoc";
            version = "0.1.0";
            format = "pyproject";

            src = ./.;

            nativeBuildInputs = [
              pkgs.makeWrapper
              python.pkgs.setuptools
            ];

            checkPhase = ''
              runHook preCheck
              ${python.interpreter} -m unittest discover -s tests
              runHook postCheck
            '';

            postInstall = ''
              wrapProgram $out/bin/memoc \
                --prefix PATH : ${pkgs.lib.makeBinPath [
                  pkgs.git
                  pkgs.ghq
                ]}
            '';

            pythonImportsCheck = [ "memory_core" ];

            meta = {
              description = "Repository memory books CLI";
              mainProgram = "memoc";
            };
          };
        }
      );

      apps = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          memoc = self.packages.${system}.default;
          memocApp = {
            type = "app";
            program = "${nixpkgs.lib.getExe memoc}";
          };
          memocSubcommandApp =
            subcommand:
            let
              app = pkgs.writeShellApplication {
                name = "memoc-${subcommand}";
                text = ''
                  exec ${nixpkgs.lib.getExe memoc} ${subcommand} "$@"
                '';
              };
            in
            {
              type = "app";
              program = "${app}/bin/memoc-${subcommand}";
            };
        in
        {
          default = memocApp;
          memoc = memocApp;
          init = memocSubcommandApp "init";
          branch = memocSubcommandApp "branch";
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.git
              pkgs.ghq
              pkgs.python312
            ];
          };
        }
      );
    };
}
