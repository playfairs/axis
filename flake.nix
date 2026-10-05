{
  description = "Axis development environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  inputs.nox.url = "github:playfairs/nox";
  inputs.nox.inputs.nixpkgs.follows = "nixpkgs";

  outputs = { nixpkgs, nox, ... }:
    let
      systems = [
        "aarch64-darwin"
        "aarch64-linux"
        "x86_64-darwin"
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      formatter = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        import ./nix/formatter.nix { inherit pkgs; });

      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = pkgs.mkShell {
            packages = [
              nox.packages.${system}.nox
              (pkgs.python3.withPackages (pythonPackages: [
                pythonPackages.cffi
              ]))
              pkgs.ruff
              pkgs.uv
              pkgs.clang
              pkgs.curl
              pkgs.pkg-config
            ];
          };
        });
    };
}
