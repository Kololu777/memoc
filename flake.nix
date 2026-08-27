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
            version = "0.2.0";
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
              mkdir -p $out/share/memoc/skills
              cp -R \
                ${./skills}/memoc-create \
                ${./skills}/memoc-write \
                $out/share/memoc/skills/

              wrapProgram $out/bin/memoc \
                --prefix PATH : ${
                  pkgs.lib.makeBinPath [
                    pkgs.git
                    pkgs.ghq
                  ]
                }
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
          context = memocSubcommandApp "context";
          migrate = memocSubcommandApp "migrate";
          list = memocSubcommandApp "list";
          read = memocSubcommandApp "read";
          write = memocSubcommandApp "write";
          doctor = memocSubcommandApp "doctor";
        }
      );

      homeManagerModules.default =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        let
          cfg = config.programs.memoc;
          system = pkgs.stdenv.hostPlatform.system;
        in
        {
          options.programs.memoc = {
            enable = lib.mkEnableOption "memoc repository memory books";

            package = lib.mkOption {
              type = lib.types.package;
              default = self.packages.${system}.default;
              description = "The memoc package, including its bundled Codex skills.";
            };

            installCodexSkills = lib.mkOption {
              type = lib.types.bool;
              default = true;
              description = "Install the bundled memoc skills for Codex.";
            };
          };

          config = lib.mkIf cfg.enable {
            home.packages = [ cfg.package ];

            home.file = lib.mkIf cfg.installCodexSkills {
              ".codex/skills/memoc-create".source = "${cfg.package}/share/memoc/skills/memoc-create";
              ".codex/skills/memoc-write".source = "${cfg.package}/share/memoc/skills/memoc-write";
            };
          };
        };

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
