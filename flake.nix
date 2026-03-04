{
  description = "GitHub App MCP shim";

  inputs = {
    devshell = {
      url = "github:numtide/devshell";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nixpkgs.url = "nixpkgs";
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      devshell,
      nixpkgs,
      treefmt-nix,
      ...
    }@inputs:
    let
      projectName = "github-mcp-shim";
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
        overlays = [
          devshell.overlays.default
        ];
      };
      lib = pkgs.lib;
      treefmtEval = treefmt-nix.lib.evalModule pkgs {
        projectRootFile = "flake.nix";
        programs = {
          nixfmt.enable = true;
          prettier.enable = true;
        };
        settings.formatter.python = {
          command = "${pkgs.bash}/bin/bash";
          options = [
            "-euc"
            ''
              ${pkgs.ruff}/bin/ruff format -q "$@" && ${pkgs.isort}/bin/isort -q --dt "$@"
            ''
            "--"
          ];
          includes = [ "*.py" ];
          excludes = [ "*/typings/*" ];
        };
      };
    in
    {
      formatter.${system} = treefmtEval.config.build.wrapper;
      checks.${system}.formatting = treefmtEval.config.build.check inputs.self;
      devShells.${system}.default = pkgs.devshell.mkShell {
        name = "${projectName}";
        motd = "{32}${projectName} activated{reset}\n$(type -p menu &>/dev/null && menu)\n";

        env = with pkgs; [
          {
            name = "XDG_STATE_HOME";
            eval = "$PRJ_ROOT/.state";
          }
          {
            name = "DATA_HOME";
            eval = "$PRJ_ROOT/.data";
          }
          {
            name = "XDG_CACHE_HOME";
            eval = "$PRJ_ROOT/.cache";
          }
          {
            name = "ANSIBLE_HOME";
            eval = "$XDG_CACHE_HOME/ansible";
          }
          {
            name = "ANSIBLE_LOCAL_TMP";
            eval = "$ANSIBLE_HOME/tmp";
          }
          {
            name = "CODEX_HOME";
            eval = "$XDG_STATE_HOME/codex";
          }
          {
            name = "CLAUDE_CONFIG_DIR";
            eval = "$XDG_STATE_HOME/claude";
          }
          {
            name = "LD_LIBRARY_PATH";
            value = lib.makeLibraryPath [
              file
              stdenv.cc.cc.lib
            ];
          }
          {
            name = "NPM_CONFIG_CACHE";
            eval = "$XDG_CACHE_HOME/npm";
          }
          {
            name = "PRE_COMMIT_HOME";
            eval = "$XDG_CACHE_HOME/pre-commit";
          }
        ];

        packages = with pkgs; [
          (python313.withPackages (
            pypkgs: with pypkgs; [
              pip
              isort
            ]
          ))
          bubblewrap
          claude-code
          codex
          gh
          nodejs_latest
          poetry
          pre-commit
          process-compose
          pyright
          typescript
          ruff
        ];

        commands = [
          {
            name = "sandbox-claude";
            command = ''
              bwrap=${lib.getExe pkgs.bubblewrap}
              GIT_SSH_COMMAND='ssh -F /dev/null -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519' \
              $bwrap --bind / / \
              --remount-ro / \
              --ro-bind /nix /nix \
              --bind "$(pwd)" "$(pwd)" \
              --chdir "$(pwd)" \
              --proc /proc \
              --dev /dev \
              --tmpfs /tmp \
              -- \
              ${lib.getExe pkgs.claude-code} --dangerously-skip-permissions'';
          }

          {
            name = "install-hooks";
            command = ''
              pushd $PRJ_ROOT
              if [[ -f ".pre-commit-config.yaml" ]]; then
                ${lib.getExe pkgs.pre-commit} install --overwrite --install-hooks
              fi
              popd
              '';
            help = "install or update pre-commit hooks";
          }

          {
            name = "format";
            command = ''
              pushd $PRJ_ROOT;
              (${lib.getExe pkgs.ruff} format -q ${projectName}/ && ${lib.getExe pkgs.isort} -q --dt ${projectName}/);
              popd'';
            help = "apply ruff, isort formatting";
          }

          {
            name = "check";
            command = ''
              ruff=${lib.getExe pkgs.ruff}
              pyright=${lib.getExe pkgs.pyright}
              pushd $PRJ_ROOT;
              echo "${projectName}"
              ($ruff check ${projectName}/ || true);
              $pyright ${projectName}/;

              if [[ -d "migrations/" ]]; then
                echo "migrations"
                ($ruff check migrations/ || true);
                $pyright migrations/;
              fi

              if [[ -d "tests/" ]]; then
                echo "tests"
                ($ruff check tests/ || true);
                $pyright tests/;
              fi
              popd'';
            help = "run ruff linter, pyright type checker";
          }

          {
            name = "up";
            command = ''
              pushd $PRJ_ROOT
              ${lib.getExe pkgs.process-compose} up
              popd
            '';
            help = "bring up services stack";
          }
        ];
      };
    };
}
