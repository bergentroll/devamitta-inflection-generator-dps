from importlib import resources
from pathlib import Path
from typing import List, Dict, Tuple, Union
import os
import pickle
import re
import webbrowser

from aksharamukha import transliterate
from pandas_ods_reader import read_ods
from rich import print  # pylint: disable=redefined-builtin
import pandas

from inflection_generator import settings
from inflection_generator.abbreviation_translator import AbbreviationTranslator
from inflection_generator.helpers import Kind, create_directories, data_frame_from_inflections_csv, excel_index, timeis
from inflection_generator.sorter import sort_key

# TODO Try to avoid global keyword in the module
# FIXME Too long, split on modules

# Globals
changed: List[str]
inflections_not_exist: List[str]
new_inflections_dict: Dict = {}
no_eg1_list: List[str]
no_eg2_list: List[str]
no_eg3_list: List[str] = []


PathType = Union[Path, str]


def convert_dpd_ods_to_csv():
    print(f"{timeis()} [yellow]converting dpd.ods to csv")
    print(f"{timeis()} ----------------------------------------")

    ods_file = settings.DPS_DIR / "dpd.ods"
    sheet_index = 1
    df = read_ods(ods_file, sheet_index, headers=False)

    df.fillna("", inplace=True)
    df = df.astype(str)  # make everting string
    df = df.drop(index=0)  # remove first row of numbers
    new_header = df.iloc[0]  # grab the first row for the header
    df = df[1:]  # take the data less the header row
    df.columns = new_header  # set the header row as the df header
    df.reset_index(drop=True, inplace=True)  # resets index to 0
    df = df.replace(to_replace=r"\.0", value="", regex=True)  # removes all flaots .0

    df.to_csv(settings.DPS_DIR / "csvs" / "dpd.csv", index=False, sep="\t", encoding="utf-8")


def create_inflection_table_index() -> pandas.DataFrame:
    print(f"{timeis()} [yellow]inflection generator")
    print(f"{timeis()} ----------------------------------------")
    print(f"{timeis()} [green]creating inflection table index")

    inflection_table_index_df = pandas.read_excel(
        settings.DECLENSIONS_AND_CONJUGATIONS_FILE,
        sheet_name="index",
        dtype=str,
        na_filter=False)

    return inflection_table_index_df


def create_inflection_table_df() -> pandas.DataFrame:
    print(f"{timeis()} [green]creating inflection table dataframe")

    inflection_table_df = pandas.read_excel(
        settings.DECLENSIONS_AND_CONJUGATIONS_FILE,
        sheet_name="declensions",
        dtype=str,
        keep_default_na=False)

    inflection_table_df = inflection_table_df.shift(periods=2)

    col_length = len(inflection_table_df.columns)
    inflection_table_df.columns = [excel_index(i) for i in range(col_length)]
    return inflection_table_df


def test_inflection_pattern_changed(
        inflection_table_index: pandas.DataFrame,
        inflection_table: pandas.DataFrame) -> None:
    print(f"{timeis()} [green]test if inflection patterns have changed")

    create_directories()
    global pattern_changed
    pattern_changed = []

    for row in range(len(inflection_table_index)):
        inflection_name = inflection_table_index.iloc[row, 0]
        cell_range = inflection_table_index.iloc[row, 1]
        like = inflection_table_index.iloc[row, 2]
        irreg = inflection_table_index.iloc[row, 3]

        col_range_1 = re.sub(r"(.+?)\d*\:.+", "\\1", cell_range)
        col_range_2 = re.sub(r".+\:(.[A-Z]*)\d*", "\\1", cell_range)
        row_range_1 = int(re.sub(r".+?(\d{1,3}):.+", "\\1", cell_range))
        row_range_2 = int(re.sub(r".+:.+?(\d{1,3})", "\\1", cell_range))

        inflection_table_df_filtered = inflection_table.loc[row_range_1:row_range_2, col_range_1:col_range_2]
        inflection_table_df_filtered.Name = inflection_name

        inflection_table_df_filtered.reset_index(drop=True, inplace=True)

        inflection_table_df_filtered.iloc[0, 0] = ""

        # replace header

        # Grab the first row for the header
        new_header = inflection_table_df_filtered.iloc[0]
        # Take the data less the header row
        inflection_table_df_filtered = inflection_table_df_filtered[1:]
        # Set the header row as the df header
        inflection_table_df_filtered.columns = new_header

        # replace index

        inflection_table_df_filtered.index = inflection_table_df_filtered.iloc[0:, 0]
        inflection_table_df_filtered = inflection_table_df_filtered.iloc[:, 1:]

        # remove unnamed column headers

        inflection_table_df_filtered = inflection_table_df_filtered.rename(
            columns=lambda x: re.sub('Unnamed.*', '', x))

        # test

        old = ''

        try:
            old = pandas.read_csv(f"output/patterns/{inflection_name}.csv", sep="\t", index_col=0, na_filter=False)
            old = old.rename(columns=lambda x: re.sub('Unnamed.*', '', x))
        except FileNotFoundError:
            print(f"{timeis()} [red]{inflection_name} - doesn't exist - added")
            pattern_changed.append(inflection_name)
            inflection_table_df_filtered.to_csv(f"output/patterns/{inflection_name}.csv", sep="\t")

        if inflection_table_df_filtered.equals(old) or inflection_name in pattern_changed:
            continue

        if not inflection_table_df_filtered.equals(old):
            print(f"{timeis()} [red]{inflection_name} - different - updated")
            inflection_table_df_filtered.to_csv(f"output/patterns/{inflection_name}.csv", sep="\t")
            pattern_changed.append(inflection_name)

    if pattern_changed == []:
        print("all patterns identical")
    if pattern_changed != []:
        print("~" * 40)
        print(f"the following patterns have changes and will be generated\n{pattern_changed}")


def create_data_frame(path: PathType) -> Tuple[pandas.DataFrame, List[str]]:
    print("~" * 40)
    print(f"create dataframe from {path}")

    dps_df = pandas.read_csv(path, sep="\t", dtype=str, na_filter=False)
    headwords_list = dps_df['pali_1'].tolist()

    print(f"{len(headwords_list)} headwords loaded")

    return dps_df, headwords_list


def test_for_missing_stem_and_pattern(dps_df: pandas.DataFrame):
    print("~" * 40)
    print("test for missing stems and patterns:")

    error = False
    missing_stem_string = ""
    missing_pattern_string = ""

    for row in range(dps_df.shape[0]):
        headword = dps_df.loc[row, 'pali_1']
        stem = dps_df.loc[row, "stem"]
        pattern = dps_df.loc[row, "pattern"]

        if stem == "":
            missing_stem_string += headword + "|"
            error = True
        if stem != "-" and pattern == "":
            missing_pattern_string += headword + "|"
            error = True

    if missing_stem_string != "":
        print(f"{timeis()} [red]words with missing stems: {missing_stem_string}")
    if missing_pattern_string != "":
        print(f"{timeis()} [red]words with missing patterns: {missing_pattern_string}")
    if error:
        input(f"{timeis()} [red]there are stem & pattern errors, please fix them before continuing")
    else:
        print("no stem & pattern errors found")


def test_for_wrong_patterns(inflection_table_index: pandas.DataFrame, dps_df: pandas.DataFrame) -> None:

    print("~" * 40)
    print("testing for wrong patterns:")

    index_patterns = inflection_table_index["inflection name"].values.tolist()

    error = False

    wrong_patten_string = ""

    for row in range(dps_df.shape[0]):
        headword = dps_df.loc[row, 'pali_1']
        stem = dps_df.loc[row, "stem"]
        pattern = dps_df.loc[row, "pattern"]

        if stem == "-":
            pass
        elif stem == "!":
            pass
        elif pattern in index_patterns:
            pass
        elif pattern not in index_patterns:
            wrong_patten_string += headword + "|"
            error = True
        else:
            pass

    if wrong_patten_string != "":
        print(f"{timeis()} [red]wrong patterns: {wrong_patten_string}")
    if error:
        input(f"{timeis()} [red]wrong patterns - fix 'em!")
    if not error:
        print("no wrong patterns found")


def test_for_differences_in_stem_and_pattern(dps_df: pandas.DataFrame) -> None:
    print("~" * 40)
    print("testing for changes in stem and pattern:")

    create_directories()

    global changed
    changed = []
    added_string = ""
    changed_string = ""

    for row in range(dps_df.shape[0]):
        headword = dps_df.loc[row, 'pali_1']
        stem = dps_df.loc[row, "stem"]
        pattern = dps_df.loc[row, "pattern"]
        old = ""
        new = f"{headword} {stem} {pattern}"

        try:
            with open(f"output/pickle test/{headword}", "rb") as pickle_file:
                old = pickle.load(pickle_file)
        except FileNotFoundError:
            added_string += headword + "|"
            changed.append(headword)
            with open(f"output/pickle test/{headword}", "wb") as pickle_file:
                pickle.dump(new,pickle_file)
            continue

        if old == new or old in changed:
            continue

        changed_string += headword + "|"
        changed.append(headword)
        pickle_file = open(f"output/pickle test/{headword}", "wb")
        pickle.dump(new, pickle_file)
        pickle_file.close()

    if added_string != "":
        print("headword / stem / pattern doesnt exist and will be added:")
        print("~" * 40)
        print(added_string)
    if changed_string != "":
        print("headword / stem / pattern has changed and will be updated")
        print("~" * 40)
        print(changed_string)
    if changed == []:
        print("no headwords stems or patterns changed")


def _test_if_inflections_exist(dps_df: pandas.DataFrame, output_dir: Path) -> None:
    global inflections_not_exist
    inflections_not_exist = []

    print("~" * 40)
    print("test if inflections exists")

    create_directories()

    for row in range(dps_df.shape[0]):
        headword = dps_df.loc[row, 'pali_1']
        path = output_dir / headword
        if not path.is_file():
            inflections_not_exist.append(headword)

    if inflections_not_exist:
        print("~"*40)
        print("inflection file doesn't exist for:")
        print("|".join(inflections_not_exist))
        print("~"*40)
    else:
        print("no missing inflection files")


def test_if_inflections_exist_suttas(dps_df: pandas.DataFrame) -> None:
    _test_if_inflections_exist(dps_df, settings.INFLECTIONS_DIR)


def test_if_inflections_exist_dps(dps_df: pandas.DataFrame) -> None:
    _test_if_inflections_exist(dps_df, settings.INFLECTIONS_TRANSLIT_DIR)


def generate_changed_inflected_forms(dps_df: pandas.DataFrame) -> None:
    print("~" * 40)
    print("generating changed inflected forms:")

    global new_inflections_dict
    new_inflections_dict = {}

    for row in range(dps_df.shape[0]):
        headword = dps_df.loc[row, 'pali_1']
        headword_clean = re.sub(r" \d*$", "", headword)
        stem = dps_df.loc[row, "stem"]
        if re.match("!.+", stem) is not None:  # stem contains "!.+" - must get inflection table but no synonsyms
            stem = "!"
        if stem == "*":
            stem = ""
        pattern = dps_df.loc[row, "pattern"]
        pos = dps_df.loc[row, 'pos']
        # metadata = dps_df.loc[row, "Metadata"]
        meaning = dps_df.loc[row, "meaning_1"]
        variant = dps_df.loc[row, "variant"]

        inflections_string = ""

        if headword in changed or pattern in pattern_changed or headword in inflections_not_exist:

            if stem == "-":
                inflections_string += headword_clean + " "

            elif stem == "!":
                inflections_string += headword_clean + " "

            else:
                inflections_string += headword_clean + " "

                try:
                    df = pandas.read_csv(f"output/patterns/{pattern}.csv", sep="\t", header=None, na_filter=False)
                    df_rows = df.shape[0]
                    df_columns = df.shape[1]

                    for rows in range(1, df_rows):
                        for columns in range(1, df_columns, 2):
                            line = df.iloc[rows, columns]
                            line = re.sub(r"(.+)", f"{stem}\\1", line)
                            search_string = re.compile("\n", re.M)
                            replace_string = " "
                            matches = re.sub(search_string, replace_string, line)
                            inflections_string += matches + " "
                except:
                    with open("inflection generator errorlog.txt", "a") as error_log:
                        error_log.write(f"error on: {headword}\n")
                        print(f"error on: {headword}\n")

            this_word_inflections = {headword: inflections_string}
            new_inflections_dict.update(this_word_inflections)

    if new_inflections_dict:
        new_inflections_df = pandas.DataFrame.from_dict(new_inflections_dict, orient='index')
        new_inflections_df.to_csv(settings.NEW_INFLECTIONS_FILE, sep="\t", header=False)

    else:
        print("no new inflections")


class InflectionTableGenerator:
    # TODO Split to module
    indeclinables = {"abbrev", "abs", "ger", "ind", "inf", "prefix"}
    conjugations = {"aor", "cond", "fut", "imp", "imperf", "opt", "perf", "pr"}
    declensions = {
        "adj", "card", "cs", "fem", "letter", "masc", "nt", "ordin",
        "pp", "pron", "prp", "ptp", "root", "suffix", "ve"}

    def __init__(self, data: pandas.DataFrame, inflection_table_index: pandas.DataFrame, kind: Kind) -> None:
        self._data = data
        self._inflection_table_index_dict = dict(
            zip(
                inflection_table_index.iloc[:, 0],
                inflection_table_index.iloc[:, 2]))
        self._kind = kind
        self._translator = AbbreviationTranslator(script='cyrl')

    def translate_table(self, data: pandas.DataFrame) -> None:
        if self._kind is Kind.DPS:
            data.columns = [self._translator.translate_string(col) for col in data.columns]
            data.index = [self._translator.translate_string(i) for i in data.index]

    def _make_heading(self, pos: str, example: str, headword_clean: str, pattern: str) -> str:
        if pos in self.declensions:
            if self._kind is Kind.DPS:
                derivative_type = "склоняется"
            else:
                derivative_type = "declension"
        elif pos in self.conjugations:
            if self._kind is Kind.DPS:
                derivative_type = "спрягается"
            else:
                derivative_type = "conjugation"

        if example:
            if self._kind is Kind.DPS:
                par_content = (
                    f"<b>{headword_clean}</b> — это <b>{pattern}</b>,"
                    f" {derivative_type} как <b>{example}</b>")
            else:
                par_content = (
                    f"<b>{headword_clean}</b> is <b>{pattern}</b>"
                    f" {derivative_type} like <b>{example}</b>")
        else:
            if self._kind is Kind.DPS:
                par_content = (
                    f"<b>{headword_clean}</b> — это <b>{pattern}</b>,"
                    f" неправильно {derivative_type}")
            else:
                par_content = (
                    f"<b>{headword_clean}</b> is <b>{pattern}</b>"
                    f" irregular {derivative_type}")

        heading = f'<p class="heading">{par_content}</p>\n'
        return heading

    def _create_html_table(self, row: int):
        headword = self._data.loc[row, 'pali_1']
        print(f"{row}\t{headword}")

        headword_clean = re.sub(r" \d*$", "", headword)

        stem = self._data.loc[row, "stem"]
        if re.match("!.+", stem) is not None:  # stem contains "!.+" - must get inflection table but no synonsyms
            stem = re.sub("!", "", stem)
        if stem == "*":
            stem = ""

        pattern = self._data.loc[row, "pattern"]
        pos = self._data.loc[row, 'pos']

        html = ''

        if stem == "-":
            html = f"<p><b>{headword_clean}</b> is indeclinable</p>"

        elif stem == "!":
            html = f"<p>click on <b>{pattern}</b> for inflection table</p>"

        else:
            df = pandas.read_csv(f"output/patterns/{pattern}.csv", sep="\t", index_col=0, na_filter=False)
            df.rename_axis(None, inplace=True)  # delete pattern name

            df_rows = df.shape[0]
            df_columns = df.shape[1]

            for rows in range(0, df_rows):
                for columns in range(0, df_columns, 2):  # 1 to 0
                    html_cell = df.iloc[rows, columns]
                    syn_cell = df.iloc[rows, columns]

                    html_cell = re.sub(r"(.+)", "<b>\\1</b>", html_cell)  # add bold
                    html_cell = re.sub(r"(.+)", f"{stem}\\1", html_cell)  # add stem
                    html_cell = re.sub(r"\n", "<br>", html_cell)  # add line breaks
                    df.iloc[rows, columns] = html_cell

                    syn_cell = re.sub(r"(.+)", f"{stem}\\1", syn_cell)
                    # FIXME following seems unused
                    # search_string = re.compile("\n", re.M)
                    # replace_string = " "
                    # matches = re.sub(search_string, replace_string, syn_cell)

            column_list = []
            for i in range(1, df_columns, 2):
                column_list.append(i)

            df.drop(df.columns[column_list], axis=1, inplace=True)
            self.translate_table(df)
            table = df.to_html(escape=False)
            table = re.sub("Unnamed.+", "", table)
            table = re.sub("NaN", "", table)

            example = self._inflection_table_index_dict[pattern]
            heading = self._make_heading(pos, example, headword_clean, pattern)

            html = heading + table

        if self._kind is Kind.DPS:
            tables_dir = settings.HTML_TABLES_DPS_DIR
        elif self._kind is Kind.SBS:
            tables_dir = settings.HTML_TABLES_SBS_DIR

        with open(tables_dir / f"{headword}.html", "w") as html_file:
            html_file.write(html)

    def generate_html(self) -> None:
        create_directories()

        print("~" * 40)
        print("generating html inflection tables")
        print("~" * 40)

        for row in range(self._data.shape[0]):
            headword = self._data.loc[row, 'pali_1']
            pattern = self._data.loc[row, "pattern"]

            if headword in changed or pattern in pattern_changed or headword in inflections_not_exist:
                self._create_html_table(row)


def generate_inflections_in_table_list(dps_df: pandas.DataFrame) -> None:
    print(f"{timeis()} [green]generating inflection lists")

    create_directories()

    indeclinables = ["abbrev", "abs", "ger", "ind", "inf", "prefix", "suffix", "cs", "letter"]
    conjugations = ["aor", "cond", "fut", "imp", "imperf", "opt", "perf", "pr"]
    declensions = ["adj", "card", "fem", "letter", "masc", "nt", "ordin", "pp", "pron", "prp", "ptp", "root", "suffix", "ve"]

    dps_df_length = dps_df.shape[0]

    for row in range(dps_df_length):
        headword = dps_df.loc[row, 'pali_1']
        headword_clean = re.sub(r" \d*$", "", headword)
        stem = dps_df.loc[row, "stem"]

        inflection_string = ""

        pattern = dps_df.loc[row, "pattern"]
        pos = dps_df.loc[row, 'pos']
        meaning = dps_df.loc[row, "meaning_1"]

        if headword in changed or pattern in pattern_changed or headword in inflections_not_exist:
            if pos not in indeclinables and pos != "idiom" and pos != "sandhi":
                if row % 1000 == 0:
                    print(f"{timeis()} {row}/{dps_df_length}\t{headword}")

                try:
                    df = pandas.read_csv(f"output/patterns/{pattern}.csv", sep="\t", index_col=0, na_filter=False)
                    df.rename_axis(None, inplace=True)  # delete pattern name
                    df_rows = df.shape[0]
                    df_columns = df.shape[1]
                except:
                    print(f"{timeis()} [red]pattern '{pattern}' not found for headword '{headword}'")
                    continue

                for rows in range(0, df_rows):
                    for columns in range(0, df_columns, 2):  # 1 to 0
                        cell = df.iloc[rows, columns]
                        if cell == "":
                            continue
                        cell = re.sub(r"(.+)", f"{stem}\\1", cell)
                        search_string = re.compile("\n", re.M)
                        replace_string = " "
                        cell = re.sub(search_string, replace_string, cell)
                        inflection_string += cell + " "

                inflection_string = re.sub("!", "", inflection_string)
                inflection_string = re.sub(r"\*", "", inflection_string)

                inflections_list = list(set(inflection_string.split(" ")))
                with open(f"output/inflections in table/{headword}", "wb") as file:
                    pickle.dump(inflections_list, file)

                with open(f"output/inflections in table/{headword}.txt", "w") as file:
                    file.write(str(inflections_list))


def transcribe_new_inflections():
    create_directories()
    if new_inflections_dict:
        print("~" * 40)

        new_inflections = open(settings.NEW_INFLECTIONS_FILE, "r")
        new_inflections_read = new_inflections.read()
        new_inflections.close()

        new_inflections_translit = open(settings.NEW_INFLECTIONS_TRANSLIT_FILE, "w")

        print("converting synonyms to RussianCyrillic")
        cyrillic = transliterate.process("IAST", "RussianCyrillic", new_inflections_read, post_options=['CyrillicPali'])

        print("converting inflections to devanagari")
        devanagari = transliterate.process(
            "IAST", "Devanagari", new_inflections_read, post_options=['DevanagariAnusvara'])

        roman = new_inflections_read.split("\n")[:-1]
        cyrillic = cyrillic.split("\n")
        devanagari = devanagari.split("\n")

        for i in zip(roman, cyrillic, devanagari):
            new_inflections_translit.write(i[0]+i[1].split("\t")[1]+i[2].split("\t")[1]+"\n")

        new_inflections_translit.close()

    else:
        print("no new inflections to transcribe")


def _combine_old_and_new_dataframes(
        all_inflections_file: Path,
        new_inflections_file: Path, diff_file: Path) -> pandas.DataFrame:
    print("~" * 40)
    print("combing old and new dataframes:")

    create_directories()

    diff = pandas.DataFrame()

    if new_inflections_dict:
        all_inflections = data_frame_from_inflections_csv(all_inflections_file)

        new_inflections = pandas.read_csv(new_inflections_file, header=None, sep="\t")

        diff = pandas.merge(all_inflections, new_inflections, on=[0], how='outer', indicator='exists')

        # Copy changed items
        test1 = diff["exists"] == "both"
        test2 = diff["1_y"] != ""
        filter = test1 & test2
        diff.loc[filter, "1_x"] = diff.loc[filter, "1_y"]

        # Add new items
        test1 = diff["exists"] == "right_only"
        test2 = diff["1_y"] != ""
        filter = test1 & test2
        diff.loc[filter, "1_x"] = diff.loc[filter, "1_y"]

        # FIXME !!! How to delete non existent?

        # Order columns
        diff = diff[[0, "1_x"]]

        diff.to_csv(all_inflections_file, sep="\t", index=None, header=False)
        print(f"{all_inflections_file} updated")

    else:
        print(f"{all_inflections_file} unchanged")

    return diff


def _export_to_pickle(output_dir: Path, diff: pandas.DataFrame, alt_anusvara=False):
    print("~" * 40)
    print(f"exporting pickles to {output_dir}")

    create_directories()

    all_inflections = diff

    for row in range(len(all_inflections)):
        headword = all_inflections.iloc[row, 0]
        inflections = all_inflections.iloc[row, 1]

        # FIXME !!! How to delete headword when no longer exists???

        if headword in new_inflections_dict.keys():
            print(headword)

            inflections_list = inflections.split()

            # add ṁ version
            if alt_anusvara:
                alt_list = [word.replace("ṃ", "ṁ") for word in inflections_list if 'ṃ' in word]
                inflections_list.extend(alt_list)

            inflections_list = list(dict.fromkeys(inflections_list))

            with open(output_dir / headword, "wb") as text_file:
                pickle.dump(inflections_list, text_file)


def combine_old_and_new_translit_dataframes() -> pandas.DataFrame:
    return _combine_old_and_new_dataframes(
        all_inflections_file=settings.ALL_INFLECTIONS_TRANSLIT_FILE,
        new_inflections_file=settings.NEW_INFLECTIONS_TRANSLIT_FILE,
        diff_file="output/diff translit.csv")


def export_translit_to_pickle(diff: pandas.DataFrame) -> None:
    _export_to_pickle(settings.INFLECTIONS_TRANSLIT_DIR, diff, alt_anusvara=True)


def combine_old_and_new_dataframes() -> pandas.DataFrame:
    return _combine_old_and_new_dataframes(
        all_inflections_file=settings.ALL_INFLECTIONS_FILE,
        new_inflections_file=settings.NEW_INFLECTIONS_FILE,
        diff_file="output/diff.csv")


def export_inflections_to_pickle(diff: pandas.DataFrame) -> None:
    _export_to_pickle(settings.INFLECTIONS_DIR, diff)


def make_list_of_all_inflections() -> None:
    print("~" * 40)
    print("creating all inflections df")

    global all_inflections_df
    all_inflections_df = pandas.read_csv(settings.ALL_INFLECTIONS_FILE, header=None, sep="\t")

    print("~" * 40)
    print("making master list of all inflections")
    print("~" * 40)

    # global all_inflections_list
    all_inflections_string = ""
    all_inflections_length = all_inflections_df.shape[0]
    for row in range(all_inflections_length):
        headword = all_inflections_df.iloc[row, 0]
        inflections = all_inflections_df.iloc[row, 1]
        all_inflections_string += inflections

        if row % 5000 == 0:
            print(f"{row} {headword}")

    all_inflections_list = all_inflections_string.split()
    all_inflections_list = list(dict.fromkeys(all_inflections_list))

    global all_inflections_set
    all_inflections_set = set(dict.fromkeys(all_inflections_list))


def make_list_of_all_inflections_no_meaning(dps_df: pandas.DataFrame) -> None:

    print("~" * 40)
    print("making list of all inflections with no meaning")
    print("~" * 40)

    global no_meaning_list

    test1 = dps_df["meaning_1"] != ""
    test2 = dps_df['pos'] != "prefix"
    test3 = dps_df['pos'] != "suffix"
    test4 = dps_df['pos'] != "cs"
    test5 = dps_df['pos'] != "ve"
    test6 = dps_df['pos'] != "idiom"
    # test7 = dps_df["Metadata"] != "yes"
    filter = test1 & test2 & test3 & test4 & test5 & test6

    no_meaning_df = dps_df[filter]

    no_meaning_headword_list = no_meaning_df['pali_1'].tolist()

    no_meaning_df = all_inflections_df[all_inflections_df[0].isin(no_meaning_headword_list)]

    no_meaning_string = ""
    all_inflections_length = all_inflections_df.shape[0]
    for row in range(all_inflections_length):
        headword = all_inflections_df.iloc[row, 0]
        inflections = all_inflections_df.iloc[row, 1]


        if row % 5000 == 0:
            print(f"{row} {headword}")

        if headword in no_meaning_headword_list:
            no_meaning_string += inflections

    no_meaning_list = no_meaning_string.split()
    no_meaning_list = list(dict.fromkeys(no_meaning_list))


def make_list_of_all_inflections_no_eg1(dps_df: pandas.DataFrame) -> None:
    print("~" * 40)
    print("making list of all inflections with no eg1")
    print("~" * 40)

    global no_eg1_list

    test1 = dps_df["sutta_1"] == ""
    test2 = dps_df["sbs_chapter_2"] != ""
    test3 = dps_df["sutta_2"] == ""
    test4 = dps_df['pos'] != "prefix"
    filter = test1 & test2 & test3 & test4
    no_eg1_df = dps_df[filter]

    no_eg1_headword_list = no_eg1_df['pali_1'].tolist()

    no_eg1_df = all_inflections_df[all_inflections_df[0].isin(no_eg1_headword_list)]

    no_eg1_string = ""
    all_inflections_length = all_inflections_df.shape[0]
    for row in range(all_inflections_length):
        headword = all_inflections_df.iloc[row, 0]
        inflections = all_inflections_df.iloc[row, 1]

        if row % 5000 == 0:
            print(f"{row} {headword}")

        if headword in no_eg1_headword_list:
            no_eg1_string += inflections

    no_eg1_list = no_eg1_string.split()
    no_eg1_list = list(dict.fromkeys(no_eg1_list))


def make_list_of_all_inflections_only_in_class(dps_df: pandas.DataFrame) -> None:
    print("~" * 40)
    print("making list of all inflections with sbs")
    print("~" * 40)

    global no_eg1_list

    test1 = dps_df['sbs_class_anki'] == "-"
    # test2 = dps_df["ru_meaning"] != ""
    # test3 = dps_df["sutta_2"] == ""
    # test4 = dps_df['pos'] != "prefix"
    filter = test1
    no_eg1_df = dps_df[filter]

    no_eg1_headword_list = no_eg1_df['pali_1'].tolist()

    no_eg1_df = all_inflections_df[all_inflections_df[0].isin(no_eg1_headword_list)]

    no_eg1_string = ""
    all_inflections_length = all_inflections_df.shape[0]
    for row in range(all_inflections_length):
        headword = all_inflections_df.iloc[row, 0]
        inflections = all_inflections_df.iloc[row, 1]

        if row % 5000 == 0:
            print(f"{row} {headword}")

        if headword in no_eg1_headword_list:
            no_eg1_string += inflections

    no_eg1_list = no_eg1_string.split()
    no_eg1_list = list(dict.fromkeys(no_eg1_list))


def make_list_of_all_inflections_already_in(dps_df: pandas.DataFrame) -> None:
    print("~" * 40)
    print("making list of all inflections with sbs")
    print("~" * 40)

    global no_eg2_list

    # if class_file_name == '2':
    #   cl_active = "1|2"

    # if class_file_name == '3':
    #   cl_active = "1|2|3"

    # if class_file_name == '4':
    #   cl_active = "1|2|3|4"

    test1 = dps_df['sbs_class_anki'] != "-"
    test2 = dps_df['sbs_class_anki'] != ""
    # test2 = dps_df["ru_meaning"] != ""
    # test3 = dps_df["sutta_2"] == ""
    # test4 = dps_df['pos'] != "prefix"
    filter = test1 & test2
    no_eg2_df = dps_df[filter]

    no_eg2_headword_list = no_eg2_df['pali_1'].tolist()

    no_eg2_df = all_inflections_df[all_inflections_df[0].isin(no_eg2_headword_list)]

    no_eg2_string = ""
    all_inflections_length = all_inflections_df.shape[0]
    for row in range(all_inflections_length):
        headword = all_inflections_df.iloc[row, 0]
        inflections = all_inflections_df.iloc[row, 1]

        if row % 5000 == 0:
            print(f"{row} {headword}")

        if headword in no_eg2_headword_list:
            no_eg2_string += inflections

    no_eg2_list = no_eg2_string.split()
    no_eg2_list = list(dict.fromkeys(no_eg2_list))


def make_list_of_all_inflections_no_eg2(dps_df: pandas.DataFrame) -> None:
    print("~" * 40)
    print("making list of all inflections with no eg2")
    print("~" * 40)

    global no_eg2_list

    test = ~dps_df["Fin"].str.contains("s")
    no_eg2_df = dps_df[test]

    no_eg2_headword_list = no_eg2_df['pali_1'].tolist()

    no_eg2_df = all_inflections_df[all_inflections_df[0].isin(no_eg2_headword_list)]

    no_eg2_string = ""
    all_inflections_length = all_inflections_df.shape[0]
    for row in range(all_inflections_length):
        headword = all_inflections_df.iloc[row, 0]
        inflections = all_inflections_df.iloc[row, 1]

        if row % 5000 == 0:
            print(f"{row} {headword}")

        if headword in no_eg2_headword_list:
            no_eg2_string += inflections

    no_eg2_list = no_eg2_string.split()
    no_eg2_list = list(dict.fromkeys(no_eg2_list))


def make_list_of_all_inflections_no_eg3(dps_df: pandas.DataFrame) -> None:
    print("~" * 40)
    print("making list of all inflections with sbs")
    print("~" * 40)

    global no_eg3_list

    test1 = dps_df['pos'] == "prefix"
    # test2 = dps_df["sbs_chapter_2"] != ""
    filter = test1
    no_eg3_df = dps_df[filter]

    no_eg3_headword_list = no_eg3_df['pali_1'].tolist()

    no_eg3_df = all_inflections_df[all_inflections_df[0].isin(no_eg3_headword_list)]

    no_eg3_string = ""
    all_inflections_length = all_inflections_df.shape[0]
    for row in range(all_inflections_length):
        headword = all_inflections_df.iloc[row, 0]
        inflections = all_inflections_df.iloc[row, 1]

        if row % 5000 == 0:
            print(f"{row} {headword}")

        if headword in no_eg3_headword_list:
            no_eg3_string += inflections

    no_eg3_list = no_eg3_string.split()
    no_eg3_list = list(dict.fromkeys(no_eg3_list))


def make_list_of_all_inflections_potential(dps_df: pandas.DataFrame, class_file_name: str) -> None:
    print("~" * 40)
    print("making list of all inflections with sbs")
    print("~" * 40)

    global no_eg3_list

    test1 = dps_df["meaning_1"] != ""
    test2 = dps_df['sbs_class_anki'] == ""
    test3 = dps_df["class"] == f"{class_file_name}"
    # test2 = dps_df["sbs_chapter_2"] != ""
    filter = test1 & test2 & test3
    no_eg3_df = dps_df[filter]

    no_eg3_headword_list = no_eg3_df['pali_1'].tolist()

    no_eg3_df = all_inflections_df[all_inflections_df[0].isin(no_eg3_headword_list)]

    no_eg3_string = ""
    all_inflections_length = all_inflections_df.shape[0]
    for row in range(all_inflections_length):
        headword = all_inflections_df.iloc[row, 0]
        inflections = all_inflections_df.iloc[row, 1]

        if row % 5000 == 0:
            print(f"{row} {headword}")

        if headword in no_eg3_headword_list:
            no_eg3_string += inflections

    no_eg3_list = no_eg3_string.split()
    no_eg3_list = list(dict.fromkeys(no_eg3_list))


def clean_machine(text):
    text = text.lower()
    text = re.sub(r"\d", "", text)
    text = re.sub(r"\.", "", text)
    text = re.sub("/", "", text)
    text = re.sub(r"\:", "", text)
    text = re.sub(r"\;", "", text)
    text = re.sub(",", " ", text)
    text = re.sub("‘", "", text)
    text = re.sub("'", "", text)
    text = re.sub(";", "", text)
    text = re.sub("’", "", text)
    text = re.sub(" ̓ ", " ", text)
    text = re.sub(r"\’", "", text)
    text = re.sub("\"", "", text)
    text = re.sub("!", "", text)
    text = re.sub(r"\?", "", text)
    text = re.sub(r"\+", "", text)
    text = re.sub("=", "", text)
    text = re.sub("﻿", "", text)
    text = re.sub("⇒", "", text)
    text = re.sub("§", " ", text)
    text = re.sub(r"\(", "", text)
    text = re.sub(r"\)", "", text)
    text = re.sub("-", "", text)
    text = re.sub("–", "", text)
    text = re.sub(r"\—", " ", text)
    text = re.sub("\t", " ", text)
    text = re.sub("…", " ", text)
    text = re.sub("–", "", text)
    # text = re.sub("\n", " \n ", text)
    text = re.sub("  ", " ", text)
    text = re.sub("^ ", "", text)
    text = re.sub("^ ", "", text)
    text = re.sub("^ ", "", text)
    text = re.sub(r"\[", "", text)
    text = re.sub(r"\]", "", text)
    text = re.sub("ṁ", "ṃ", text)
    text = re.sub("〈", "", text)
    text = re.sub("〉", "", text)
    text = re.sub(r"\*", "", text)
    text = re.sub("☸", "", text)
    # text = re.sub("\n", "  ", text)
    text = re.sub("suttaṃ", "suttaṃ\n", text)
    text = re.sub("next", "next\n", text)

    return text


def read_and_clean_sutta_text() -> Tuple[str, str]:
    create_directories()

    print("~" * 40)
    print("reading and cleaning sutta file")
    print("~" * 40)

    input_path = settings.CSCD_DIR
    output_path = settings.HTML_SUTTAS_DIR

    sutta_dict = pandas.read_csv(
        'sutta corespondence tables/sutta correspondence tables.csv',
        sep="\t",
        index_col=0,
        squeeze=True).to_dict(orient='index',)

    while True:
        sutta_number = input("enter sutta number: ")
        if sutta_number in sutta_dict.keys():
            break
        else:
            print("sutta number not recognised, please try again")

    sutta_file = sutta_dict.get(sutta_number).get("mūla")
    commentary_file = sutta_dict.get(sutta_number).get("aṭṭhakathā")
    sub_commentary_file = sutta_dict.get(sutta_number).get("ṭīkā")

    with open(input_path / sutta_file, 'r') as input_file:
        sutta_text = input_file.read()

    sutta_text = clean_machine(sutta_text)

    with open(output_path / sutta_file, "w") as output_file:
        output_file.write(sutta_text)

    # Commentaries

    with open(input_path / commentary_file, 'r') as input_file:
        commentary_text = input_file.read()

    commentary_text = clean_machine(commentary_text)

    with open(output_path / commentary_file, "w") as output_file:
        output_file.write(commentary_text)

    return sutta_file, commentary_file


def make_comparison_table(sutta_file: str, commentary_file: str) -> None:
    print("~" * 40)
    print("making sutta comparison table")

    output_path = settings.HTML_SUTTAS_DIR

    with open(output_path / sutta_file) as text_to_split:
        word_llst = [word for line in text_to_split for word in line.split(" ")]

    global sutta_words_df
    sutta_words_df = pandas.DataFrame(word_llst)

    inflection_test = sutta_words_df[0].isin(all_inflections_set)
    sutta_words_df["Inflection"] = inflection_test

    no_meaning_test = sutta_words_df[0].isin(no_meaning_list)
    sutta_words_df["Meaning"] = no_meaning_test

    eg1_test = sutta_words_df[0].isin(no_eg1_list)
    sutta_words_df["Eg1"] = ~eg1_test

    eg2_test = sutta_words_df[0].isin(no_eg2_list)
    sutta_words_df["Eg2"] = ~eg2_test

    eg3_test = sutta_words_df[0].isin(no_eg3_list)
    sutta_words_df["Eg3"] = ~eg3_test

    sutta_words_df.rename(columns={0: "Pali"}, inplace=True)

    sutta_words_df.drop_duplicates(subset=["Pali"], keep="first", inplace=True)

    with open(output_path / f"{sutta_file}.csv", 'w') as txt_file:
        sutta_words_df.to_csv(txt_file, header=True, index=True, sep="\t")

    print("~" * 40)
    print("making commentary comparison table")

    with open(output_path / commentary_file) as text_to_split:
        word_llst = [word for line in text_to_split for word in line.split(" ")]

    global commentary_words_df
    commentary_words_df = pandas.DataFrame(word_llst)

    inflection_test = commentary_words_df[0].isin(all_inflections_set)
    commentary_words_df["Inflection"] = inflection_test

    no_meaning_test = commentary_words_df[0].isin(no_meaning_list)
    commentary_words_df["Meaning"] = no_meaning_test

    commentary_words_df.rename(columns={0: "Pali"}, inplace=True)

    commentary_words_df.drop_duplicates(subset=["Pali"], keep="first", inplace=True)

    with open(output_path / f"{commentary_file}.csv", 'w') as txt_file:
        commentary_words_df.to_csv(txt_file, header=True, index=True, sep="\t")


def html_find_and_replace(sutta_file: str) -> None:
    print("~" * 40)
    print("finding and replacing sutta html")
    print("~" * 40)

    output_path = settings.HTML_SUTTAS_DIR

    global sutta_text
    global commentary_text

    no_meaning = []
    no_eg1 = []
    no_eg2 = []
    no_eg3 = []

    with open(output_path / sutta_file, 'r') as input_file:
        sutta_text = input_file.read()

    max_row = sutta_words_df.shape[0]
    row = 0

    for word in range(row, max_row):
        pali_word = str(sutta_words_df.iloc[row, 0])
        inflection_exists = str(sutta_words_df.iloc[row, 1])
        meaning_exists = str(sutta_words_df.iloc[row, 2])
        eg1_exists = str(sutta_words_df.iloc[row, 3])
        eg2_exists = str(sutta_words_df.iloc[row, 4])
        eg3_exists = str(sutta_words_df.iloc[row, 5])

        if row % 250 == 0:
            print(f"{row}/{max_row}\t{pali_word}")

        row += 1

        if meaning_exists == "False":
            sutta_text = re.sub(fr"(^|\s)({pali_word})(\s|\n|$)", r'\\1<span class="highlight">\\2</span>\\3', sutta_text)
            no_meaning.append(pali_word)

        elif eg1_exists == "False":
            sutta_text = re.sub(fr"(^|\s)({pali_word})(\s|\n|$)", r'\\1<span class="red">\\2</span>\\3', sutta_text)
            no_eg1.append(pali_word)

        elif eg2_exists == "False":
            sutta_text = re.sub(fr"(^|\s)({pali_word})(\s|\n|$)", r'\\1<span class="green">\\2</span>\\3', sutta_text)
            no_eg2.append(pali_word)

        elif eg3_exists == "False":
            sutta_text = re.sub(fr"(^|\s)({pali_word})(\s|\n|$)", r'\\1<span class="blue">\\2</span>\\3', sutta_text)
            no_eg3.append(pali_word)

    sutta_text = re.sub("\n", "<br><br>", sutta_text)
    sutta_text += f'<br><br>no meanings: <span class="highlight">{" ".join(no_meaning)}</span>'
    sutta_text += f'<br><br>no eg1: <span class="red">{" ".join(no_eg1)}</span>'
    sutta_text += f'<br><br>no eg2: <span class="green">{" ".join(no_eg2)}</span>'
    sutta_text += f'<br><br>no eg3: <span class="blue">{" ".join(no_eg3)}</span>'


def write_html(sutta_file: str) -> None:
    create_directories()

    output_path = settings.HTML_SUTTAS_DIR
    html1 = resources.read_text(__package__, 'part1.html')

    # html2 = """</div><div id="right">"""

    html3 = """</div></div>"""

    html_file = open(output_path / f"{sutta_file}.html", "w")
    html_file = open(output_path / f"{sutta_file}.html", "a")
    html_file.write(html1)
    html_file.write(sutta_text)
    # html_file.write(html2)
    # html_file.write(commentary_text)
    html_file.write(html3)
    html_file.close()


def open_in_browser(sutta_file: str) -> None:
    webbrowser.open(f'output/html suttas/{sutta_file}.html')


def delete_old_pickle_files(headwords: List[str]):
    print(f"{timeis()} [green]deleting old pickle files ")

    for _root, _dirs, files in os.walk("output/pickle test", topdown=True):
        for file in files:
            try:
                if file not in headwords:
                    os.remove(f"output/pickle test/{file}")
                    print(f"{timeis()} {file}")
            except FileNotFoundError:
                print(f"{timeis()} [red]{file} not found")


def delete_unused_inflection_patterns(inflection_table_index):
    print(f"{timeis()} [green]deleting unused inflection patterns")

    inflection_patterns_list = inflection_table_index["inflection name"].tolist()
    for _root, _dirs, files in os.walk("output/patterns", topdown=True):
        for file in files:
            file_clean = re.sub(".csv", "", file)
            if file_clean not in inflection_patterns_list:
                try:
                    os.remove(f"output/patterns/{file}")
                except FileNotFoundError:
                    print(f"{timeis()} [red]{file} not found")
                else:
                    print(f"{timeis()} {file}")


def _delete_unused_html_tables(path, headwords: List[str]) -> None:
    for _root, _dirs, files in os.walk(path, topdown=True):
        for file in files:
            basename = file.removesuffix(".html")
            if basename not in headwords:
                try:
                    os.remove(path / file)
                except FileNotFoundError:
                    print(f"{timeis()} [red]{file} not found")
                else:
                    print(f"{timeis()} {file}")


def delete_unused_html_tables(headwords):
    print(f"{timeis()} [green]deleting unused html files ")
    for path in [settings.HTML_TABLES_DPS_DIR, settings.HTML_TABLES_SBS_DIR]:
        _delete_unused_html_tables(path, headwords)


def delete_unused_inflections(headwords: List[str]):
    print(f"{timeis()} [green]deleting unused inflections")

    for _root, _dirs, files in os.walk(settings.INFLECTIONS_DIR, topdown=True):
        for file in files:
            if file not in headwords:
                try:
                    os.remove(settings.INFLECTIONS_DIR / file)
                except FileNotFoundError:
                    print(f"{timeis()} [red]{file} not found")
                else:
                    print(f"{timeis()} {file}")


def delete_unused_inflections_translit(headwords: List[str]):
    print(f"{timeis()} [green]deleting unused inflections translit")

    for _root, _dirs, files in os.walk(settings.INFLECTIONS_TRANSLIT_DIR, topdown=True):
        for file in files:
            if file not in headwords:
                try:
                    os.remove(settings.INFLECTIONS_TRANSLIT_DIR / file)
                except FileNotFoundError:
                    print(f"{timeis()} [red]{file} not found")
                else:
                    print(f"{timeis()} {file}")
