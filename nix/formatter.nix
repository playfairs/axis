{ pkgs }:
pkgs.writeShellApplication {
  name = "format-bot";
  runtimeInputs = [ pkgs.ruff ];
  text = ''
    if (( $# == 0 )); then
      ruff format bot
    else
      ruff format "$@"
    fi
  '';
}