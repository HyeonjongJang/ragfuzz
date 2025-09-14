#include <stdio.h>
#include <yaml.h>

int main(void){
  static unsigned char buf[1<<20];
  size_t n = fread(buf,1,sizeof(buf),stdin);
  if(!n) return 0;

  yaml_parser_t parser;
  yaml_document_t document;
  if(!yaml_parser_initialize(&parser)) return 0;
  yaml_parser_set_input_string(&parser, buf, n);

  if(yaml_parser_load(&parser, &document)){
    yaml_document_delete(&document);
  }
  yaml_parser_delete(&parser);
  return 0;
}
