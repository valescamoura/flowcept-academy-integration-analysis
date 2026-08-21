git submodule add https://github.com/academy-agents/academy-flowcept event_log_observability/

git submodule update --remote --merge

git rm -f <CAMINHO_DA_PASTA>


git push --recurse-submodules=check

seguir README de la 

cd event_log_observability/src


FIX THIS
pip install pandas
pip install pyarrow
pip install bson -------> pip install "flowcept[extras]"


pyenv virtualenv 3.11.13 elo_venv
source ~/.pyenv/versions/elo_venv/bin/activate